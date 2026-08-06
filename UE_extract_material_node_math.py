#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ue_material_parser.py
从虚幻引擎材质编辑器复制出的纯文本中提取节点运算关系，生成伪代码。

Copyright (c) 2026 iZerat
License: MIT
GitHub: https://github.com/iZerat/UE_analyze_material_node
"""

import os
import re
import sys
import glob


# =============================================================================
# 常量与映射
# =============================================================================

PIN_NAME_MAP = {
    '基础颜色': 'BaseColor',
    'Metallic': 'Metallic',
    '高光度': 'Specular',
    '粗糙度': 'Roughness',
    '各向异性': 'Anisotropy',
    '自发光颜色': 'EmissiveColor',
    '不透明度': 'Opacity',
    '不透明蒙版': 'OpacityMask',
    'Normal': 'Normal',
    '切线': 'Tangent',
    '全局位置偏移': 'WorldPositionOffset',
    'Subsurface Color': 'SubsurfaceColor',
    'Clear Coat': 'ClearCoat',
    'Clear Coat Roughness': 'ClearCoatRoughness',
    '环境光遮挡': 'AmbientOcclusion',
    '折射 (Disabled)': 'Refraction',
    'Customized UV0': 'CustomizedUV0',
    'Customized UV1': 'CustomizedUV1',
    'Customized UV2': 'CustomizedUV2',
    'Customized UV3': 'CustomizedUV3',
    'Customized UV4': 'CustomizedUV4',
    'Customized UV5': 'CustomizedUV5',
    'Customized UV6': 'CustomizedUV6',
    'Customized UV7': 'CustomizedUV7',
    '像素深度偏移': 'PixelDepthOffset',
    '着色模型': 'ShadingModel',
    '表面厚度': 'SurfaceThickness',
    '前方材质': 'FrontMaterial',
    '置换': 'Displacement',
    '材质属性': 'MaterialAttributes',
}


# =============================================================================
# 工具函数
# =============================================================================

def split_top_level(s, delimiter):
    """按 delimiter 分割字符串，但忽略引号与括号内的 delimiter"""
    parts = []
    current = ''
    depth = 0
    in_quote = False
    quote_char = None

    for c in s:
        if in_quote:
            current += c
            if c == quote_char:
                in_quote = False
                quote_char = None
            continue

        if c in '"\'':
            in_quote = True
            quote_char = c
            current += c
            continue

        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1

        if c == delimiter and depth == 0:
            parts.append(current.strip())
            current = ''
        else:
            current += c

    if current.strip():
        parts.append(current.strip())
    return parts


def extract_node_name(expr_str):
    """从 Expression="/Script/Engine.XXX'NodeName.ExpressionName'" 提取节点名"""
    if not expr_str:
        return None
    m = re.search(r"'([^']+)'", expr_str)
    if m:
        return m.group(1).split('.')[0]
    return None


def get_output_name_by_index(node, idx):
    """根据节点输出索引获取输出通道名（如 Metallic / RGB 等）"""
    props = node.get('properties', {})
    outs = props.get('Outputs', {})
    if isinstance(outs, dict) and idx in outs:
        return outs[idx].get('OutputName')
    func_outs = props.get('FunctionOutputs', {})
    if isinstance(func_outs, dict) and idx in func_outs:
        return func_outs[idx].get('OutputName', f'Out{idx}')
    defaults = {0: 'RGB', 1: 'R', 2: 'G', 3: 'B', 4: 'A', 5: 'RGBA'}
    return defaults.get(idx, f'Out{idx}')


def translate_pin_name(pin_name):
    """将中文 Pin 名翻译为英文材质属性名"""
    return PIN_NAME_MAP.get(pin_name, pin_name)


def get_switch_input_index(pin_name):
    """将 UE Switch 节点的 Input/Input2/Input3... 映射为 0-based 索引"""
    if pin_name == 'Input':
        return 0
    if pin_name.startswith('Input'):
        suffix = pin_name[5:]  # 去掉 'Input' 前缀
        try:
            # Input2 -> 1, Input3 -> 2, ...
            return int(suffix) - 1
        except ValueError:
            pass
    return pin_name


# =============================================================================
# 解析函数
# =============================================================================

def parse_inline_struct(content):
    """解析 (Key=Value,Key2=(...)) 形式的内联结构"""
    result = {}
    if not content:
        return result
    pairs = split_top_level(content, ',')
    for pair in pairs:
        if '=' not in pair:
            continue
        k, v = pair.split('=', 1)
        k = k.strip()
        v = v.strip()
        if v.startswith('(') and v.endswith(')'):
            v = parse_inline_struct(v[1:-1])
        elif v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        elif v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        result[k] = v
    return result


def parse_property_line(line):
    """解析单行属性，返回 (key, value) 或 None"""
    # 数组项：FunctionInputs(0)=(...)
    m = re.match(r'^(\w+)\((\d+)\)=\((.*)\)$', line)
    if m:
        return m.group(1), {int(m.group(2)): parse_inline_struct(m.group(3))}

    # 普通括号属性：A=(Expression="...")
    m = re.match(r'^([A-Za-z0-9_]+)=\((.*)\)$', line)
    if m:
        return m.group(1), parse_inline_struct(m.group(2))

    # 引号字符串属性：ParameterName="Base Texture"
    m = re.match(r'^([A-Za-z0-9_]+)="([^"]*)"$', line)
    if m:
        return m.group(1), m.group(2)

    # 数值/标识符属性：R=0.409714 或 SamplerType=SAMPLERTYPE_Normal
    m = re.match(r'^([A-Za-z0-9_]+)=([^\s].*)$', line)
    if m:
        k, v = m.group(1), m.group(2)
        try:
            if '.' in v:
                v = float(v)
            else:
                v = int(v)
        except ValueError:
            pass
        return k, v

    return None


def parse_pin(line):
    """解析 CustomProperties Pin (...) 行"""
    m = re.search(r'Pin \((.*)\)', line)
    if not m:
        return {}
    content = m.group(1)
    pin = {}
    pairs = split_top_level(content, ',')
    for pair in pairs:
        if '=' not in pair:
            continue
        k, v = pair.split('=', 1)
        k = k.strip()
        v = v.strip()
        if k == 'LinkedTo':
            inner = v[1:-1] if v.startswith('(') and v.endswith(')') else v
            refs = []
            for rp in split_top_level(inner, ','):
                rp = rp.strip()
                if rp:
                    parts = rp.split()
                    if parts:
                        refs.append(parts[0])
            pin['LinkedTo'] = refs
        elif v.startswith('"') and v.endswith('"'):
            pin[k] = v[1:-1]
        else:
            pin[k] = v
    return pin


def parse_node_block(node_name, lines):
    """解析单个 MaterialGraphNode 文本块"""
    node = {
        'name': node_name,
        'expr_type': None,
        'expr_name': None,
        'properties': {},
        'pins': []
    }

    for raw_line in lines:
        line = raw_line.strip()

        if line.startswith('Begin Object Class=/Script/Engine.'):
            m = re.search(r'Class=/Script/Engine\.(\S+)', line)
            if m and not node['expr_type']:
                node['expr_type'] = m.group(1)
                m2 = re.search(r'Name="([^"]+)"', line)
                if m2:
                    node['expr_name'] = m2.group(1)
            continue

        if line.startswith('MaterialExpression="'):
            m = re.search(r'MaterialExpression="([^"]+)"', line)
            if m:
                node['expr_ref'] = m.group(1)
            continue

        if line.startswith('Begin Object') or line.startswith('End Object'):
            continue

        if line.startswith('CustomProperties Pin'):
            pin = parse_pin(line)
            if pin:
                node['pins'].append(pin)
            continue

        prop = parse_property_line(line)
        if prop:
            k, v = prop
            if k in node['properties']:
                # 数组型属性（如 FunctionInputs、Outputs）需要合并
                if isinstance(v, dict) and isinstance(node['properties'][k], dict):
                    node['properties'][k].update(v)
                # 否则保留先出现的值
            else:
                node['properties'][k] = v

    return node


def parse_nodes(text):
    """解析完整文本，返回 {node_name: node_dict}"""
    nodes = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('Begin Object Class=/Script/UnrealEd.MaterialGraphNode'):
            m = re.search(r'Name="([^"]+)"', line)
            node_name = m.group(1) if m else f'Unknown_{i}'
            block_lines = []
            depth = 1
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                lstrip = lines[i].strip()
                if lstrip.startswith('Begin Object'):
                    depth += 1
                elif lstrip.startswith('End Object'):
                    depth -= 1
                i += 1
            # 去掉最后一个 End Object 行
            node = parse_node_block(node_name, block_lines[:-1])
            nodes[node_name] = node
        else:
            i += 1
    return nodes


# =============================================================================
# 伪代码生成
# =============================================================================

def get_node_input(node, input_name, nodes, visited):
    """获取节点指定输入的伪代码字符串"""
    props = node.get('properties', {})
    expr_type = node.get('expr_type', '')

    # 部分节点的属性名与接口名映射
    prop_name = input_name
    if expr_type in ('MaterialExpressionStaticSwitchParameter',
                     'MaterialExpressionStaticSwitch',
                     'MaterialExpressionLinearInterpolate'):
        if input_name == 'True':
            prop_name = 'A'
        elif input_name == 'False':
            prop_name = 'B'

    # 1) 优先从属性中的 Expression 引用获取
    prop_val = props.get(prop_name, None)
    if isinstance(prop_val, dict) and 'Expression' in prop_val:
        src = extract_node_name(prop_val['Expression'])
        if src:
            suffix = ''
            if 'OutputIndex' in prop_val:
                idx = prop_val['OutputIndex']
                src_node = nodes.get(src)
                if src_node:
                    out_name = get_output_name_by_index(src_node, idx)
                    if out_name:
                        suffix = f'.{out_name}'
            return build_expression(src, nodes, visited.copy()) + suffix

    # 2) 从 ConstX 默认值获取（如 ConstA / ConstB / ConstAlpha）
    const_key = f'Const{prop_name}'
    if const_key in props:
        return str(props[const_key])

    # 3) 从 Pin 连线获取
    for pin in node.get('pins', []):
        pin_name = pin.get('PinName', '')
        if pin_name == input_name:
            linked = pin.get('LinkedTo', [])
            if linked:
                return build_expression(linked[0], nodes, visited.copy())
            default = pin.get('DefaultValue', '')
            if default:
                return f'Constant({default})'

    return 'None'


def build_expression(node_id, nodes, visited, inline_reroutes=False):
    """递归构建单个节点的伪代码表达式"""
    if not node_id or node_id in visited:
        return f'/* ref: {node_id} */'
    visited.add(node_id)

    if node_id not in nodes:
        return f'/* missing: {node_id} */'

    node = nodes[node_id]
    expr_type = node.get('expr_type', 'Unknown')
    props = node.get('properties', {})

    # ------------------------------------------------------------------
    # 透传 / 变量引用
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionNamedRerouteDeclaration':
        name = props.get('Name', node_id)
        if inline_reroutes:
            return get_node_input(node, 'Input', nodes, visited.copy())
        return name

    if expr_type == 'MaterialExpressionNamedRerouteUsage':
        decl = props.get('Declaration', '')
        m = re.search(r"MaterialExpressionNamedRerouteDeclaration'([^']+)'", decl)
        if m:
            decl_id = m.group(1).split('.')[0]
            decl_node = nodes.get(decl_id)
            if decl_node:
                return decl_node['properties'].get('Name', decl_id)
        return 'NamedRerouteUsage'

    if expr_type == 'MaterialExpressionReroute':
        return get_node_input(node, 'InputPin', nodes, visited.copy())

    # ------------------------------------------------------------------
    # 常量 / 参数
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionConstant':
        r = props.get('R', '0')
        return f'Constant({r})'

    if expr_type == 'MaterialExpressionConstant2Vector':
        dv = props.get('Constant', props.get('DefaultValue', {}))
        if isinstance(dv, dict):
            r, g = dv.get('R', '0'), dv.get('G', '0')
            return f'float2({r}, {g})'
        return 'float2(0,0)'

    if expr_type == 'MaterialExpressionConstant3Vector':
        dv = props.get('Constant', props.get('DefaultValue', {}))
        if isinstance(dv, dict):
            r, g, b = dv.get('R', '0'), dv.get('G', '0'), dv.get('B', '0')
            return f'float3({r}, {g}, {b})'
        return 'float3(0,0,0)'

    if expr_type == 'MaterialExpressionConstant4Vector':
        dv = props.get('Constant', props.get('DefaultValue', {}))
        if isinstance(dv, dict):
            r, g, b, a = dv.get('R', '0'), dv.get('G', '0'), dv.get('B', '0'), dv.get('A', '1')
            return f'float4({r}, {g}, {b}, {a})'
        return 'float4(0,0,0,1)'

    if expr_type == 'MaterialExpressionScalarParameter':
        param = props.get('ParameterName', 'Unknown')
        default = props.get('DefaultValue', props.get('R', '0'))
        return f'ScalarParameter("{param}", Default={default})'

    if expr_type == 'MaterialExpressionVectorParameter':
        param = props.get('ParameterName', 'Unknown')
        dv = props.get('DefaultValue', {})
        if isinstance(dv, dict):
            r, g, b, a = dv.get('R', '0'), dv.get('G', '0'), dv.get('B', '0'), dv.get('A', '1')
            return f'VectorParameter("{param}", Default=({r},{g},{b},{a}))'
        return f'VectorParameter("{param}")'

    if expr_type == 'MaterialExpressionTextureSampleParameter2D':
        param = props.get('ParameterName', 'Unknown')
        tex = props.get('Texture', 'None')
        tex_name = tex.split('.')[-1].strip("'") if '.' in tex else tex
        tex_name = tex_name.replace("'", "")
        uv = get_node_input(node, 'UVs', nodes, visited.copy())
        if uv != 'None':
            return f'TextureSampleParameter2D("{param}", Texture="{tex_name}", UVs={uv})'
        return f'TextureSampleParameter2D("{param}", Texture="{tex_name}")'

    # ------------------------------------------------------------------
    # 运算节点
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionLinearInterpolate':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        alpha = get_node_input(node, 'Alpha', nodes, visited.copy())
        return f'Lerp({a}, {b}, {alpha})'

    if expr_type == 'MaterialExpressionIf':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        parts = [f'A={a}', f'B={b}']
        for branch_name, pin_key in (('AGreaterThanB', 'AGreaterThanB'),
                                     ('AEqualsB', 'AEqualsB'),
                                     ('ALessThanB', 'ALessThanB')):
            val = get_node_input(node, pin_key, nodes, visited.copy())
            if val != 'None':
                parts.append(f'{branch_name}={val}')
        return f'If({", ".join(parts)})'

    if expr_type == 'MaterialExpressionAdd':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Add({a}, {b})'

    if expr_type == 'MaterialExpressionMultiply':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Multiply({a}, {b})'

    if expr_type == 'MaterialExpressionSubtract':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Subtract({a}, {b})'

    if expr_type == 'MaterialExpressionDivide':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Divide({a}, {b})'

    if expr_type == 'MaterialExpressionDesaturation':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        frac = get_node_input(node, 'Fraction', nodes, visited.copy())
        return f'Desaturate({inp}, {frac})'

    if expr_type == 'MaterialExpressionPower':
        base = get_node_input(node, 'Base', nodes, visited.copy())
        exp = get_node_input(node, 'Exponent', nodes, visited.copy())
        return f'Power({base}, {exp})'

    if expr_type == 'MaterialExpressionOneMinus':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        return f'OneMinus({inp})'

    if expr_type == 'MaterialExpressionFresnel':
        exp = get_node_input(node, 'Exponent', nodes, visited.copy())
        base = get_node_input(node, 'BaseReflectFraction', nodes, visited.copy())
        return f'Fresnel({exp}, {base})'

    # ------------------------------------------------------------------
    # 分支 / Switch
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionStaticSwitchParameter':
        param = props.get('ParameterName', None)
        # 如果没有 ParameterName，使用 expr_name 作为实际名称（保留原始命名如 StaticSwitchParameter_0）
        if not param:
            param = node.get('expr_name', 'Unknown')
        default = props.get('DefaultValue', 'false')
        true_b = get_node_input(node, 'A', nodes, visited.copy())
        false_b = get_node_input(node, 'B', nodes, visited.copy())
        return f'StaticSwitchParameter("{param}", True={true_b}, False={false_b}, Default={default})'

    if expr_type == 'MaterialExpressionStaticSwitch':
        true_b = get_node_input(node, 'A', nodes, visited.copy())
        false_b = get_node_input(node, 'B', nodes, visited.copy())
        return f'StaticSwitch(True={true_b}, False={false_b})'

    if expr_type == 'MaterialExpressionStaticBool':
        val = props.get('Value', 'false')
        return f'StaticBool({val})'

    if expr_type == 'MaterialExpressionStaticBoolParameter':
        param = props.get('ParameterName', 'Unknown')
        default = props.get('DefaultValue', 'false')
        return f'StaticBoolParameter("{param}", Default={default})'

    if expr_type == 'MaterialExpressionSwitch':
        switch_val = get_node_input(node, 'SwitchValue', nodes, visited.copy())
        default = get_node_input(node, 'Default', nodes, visited.copy())
        inputs = [f'SwitchValue={switch_val}', f'Default={default}']
        # 收集所有 Input / Input2 / Input3 ... 引脚，映射为 0-based 索引
        for pin in node.get('pins', []):
            pin_name = pin.get('PinName', '')
            idx = get_switch_input_index(pin_name)
            if isinstance(idx, int):
                linked = pin.get('LinkedTo', [])
                if linked:
                    val = build_expression(linked[0], nodes, visited.copy())
                else:
                    val = pin.get('DefaultValue', 'None')
                    if val:
                        val = f'Constant({val})'
                    else:
                        val = 'None'
                inputs.append(f'Input{idx}={val}')
        return f'Switch({", ".join(inputs)})'

    if expr_type == 'MaterialExpressionShadingPathSwitch':
        default = get_node_input(node, 'Default', nodes, visited.copy())
        branches = [f'Default={default}']
        inputs_dict = props.get('Inputs', {})
        if isinstance(inputs_dict, dict):
            for idx in sorted(inputs_dict.keys()):
                inp = inputs_dict[idx]
                if isinstance(inp, dict) and 'Expression' in inp:
                    src = extract_node_name(inp['Expression'])
                    if src:
                        pseudo = build_expression(src, nodes, visited.copy())
                        branches.append(f'Input{idx}={pseudo}')
        return f'ShadingPathSwitch({", ".join(branches)})'

    # ------------------------------------------------------------------
    # 材质函数调用
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionMaterialFunctionCall':
        func_path = props.get('MaterialFunction', 'Unknown')
        func_name = func_path.split('.')[-1].strip("'") if '.' in func_path else func_path
        func_name = func_name.replace("'", "")

        inputs = []
        func_inputs = props.get('FunctionInputs', {})
        if isinstance(func_inputs, dict):
            for idx in sorted(func_inputs.keys()):
                finp = func_inputs[idx]
                if isinstance(finp, dict):
                    input_name = finp.get('InputName', f'Input{idx}')
                    input_expr_obj = finp.get('Input', {})
                    if isinstance(input_expr_obj, dict):
                        expr_str = input_expr_obj.get('Expression', '')
                        src = extract_node_name(expr_str)
                        pseudo = build_expression(src, nodes, visited.copy()) if src else 'None'
                    else:
                        pseudo = str(input_expr_obj)
                    inputs.append(f'{input_name}={pseudo}')

        outputs = []
        func_outputs = props.get('FunctionOutputs', {})
        if isinstance(func_outputs, dict):
            for idx in sorted(func_outputs.keys()):
                fout = func_outputs[idx]
                if isinstance(fout, dict):
                    outputs.append(fout.get('OutputName', f'Out{idx}'))

        out_str = outputs[0] if outputs else 'Result'
        return f'{out_str} = {func_name}({", ".join(inputs)})'

    # ------------------------------------------------------------------
    # 其他常见节点
    # ------------------------------------------------------------------
    if expr_type == 'MaterialExpressionEyeAdaptationInverse':
        light = get_node_input(node, 'LightValueInput', nodes, visited.copy())
        alpha = get_node_input(node, 'AlphaInput', nodes, visited.copy())
        return f'EyeAdaptationInverse({light}, {alpha})'

    if expr_type == 'MaterialExpressionEyeAdaptation':
        light = get_node_input(node, 'LightValueInput', nodes, visited.copy())
        alpha = get_node_input(node, 'AlphaInput', nodes, visited.copy())
        return f'EyeAdaptation({light}, {alpha})'

    if expr_type == 'MaterialExpressionClearCoatNormalCustomOutput':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        return f'ClearCoatNormal({inp})'

    if expr_type == 'MaterialExpressionTextureCoordinate':
        idx = props.get('CoordinateIndex', '0')
        return f'TextureCoordinate({idx})'

    if expr_type == 'MaterialExpressionSceneTexture':
        tex_id = props.get('SceneTextureId', 'Unknown')
        return f'SceneTexture({tex_id})'

    if expr_type == 'MaterialExpressionSceneDepth':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        if inp != 'None':
            return f'SceneDepth({inp})'
        return 'SceneDepth'

    if expr_type == 'MaterialExpressionSaturate':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        return f'Saturate({inp})'

    if expr_type == 'MaterialExpressionWorldPosition':
        return 'WorldPosition'

    if expr_type == 'MaterialExpressionVertexNormalWS':
        return 'VertexNormalWS'

    if expr_type == 'MaterialExpressionPixelNormalWS':
        return 'PixelNormalWS'

    if expr_type == 'MaterialExpressionCameraVector':
        return 'CameraVector'

    if expr_type == 'MaterialExpressionReflectionVector':
        return 'ReflectionVector'

    if expr_type == 'MaterialExpressionNormalize':
        inp = get_node_input(node, 'VectorInput', nodes, visited.copy())
        return f'Normalize({inp})'

    if expr_type == 'MaterialExpressionComponentMask':
        inp = get_node_input(node, 'Input', nodes, visited.copy())
        r = props.get('R', 'False')
        g = props.get('G', 'False')
        b = props.get('B', 'False')
        a = props.get('A', 'False')
        return f'ComponentMask({inp}, R={r}, G={g}, B={b}, A={a})'

    if expr_type == 'MaterialExpressionAppendVector':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Append({a}, {b})'

    if expr_type == 'MaterialExpressionDotProduct':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Dot({a}, {b})'

    if expr_type == 'MaterialExpressionCrossProduct':
        a = get_node_input(node, 'A', nodes, visited.copy())
        b = get_node_input(node, 'B', nodes, visited.copy())
        return f'Cross({a}, {b})'

    if expr_type == 'MaterialExpressionCustom':
        code = props.get('Code', '')
        desc = props.get('Description', expr_type)
        inputs = []
        custom_inputs = props.get('Inputs', {})
        if isinstance(custom_inputs, dict):
            for idx in sorted(custom_inputs.keys()):
                cinp = custom_inputs[idx]
                if isinstance(cinp, dict):
                    iname = cinp.get('InputName', f'Input{idx}')
                    expr_str = cinp.get('Expression', '')
                    src = extract_node_name(expr_str)
                    pseudo = build_expression(src, nodes, visited.copy()) if src else 'None'
                    inputs.append(f'{iname}={pseudo}')
        return f'Custom("{desc}", {", ".join(inputs)}) /* {code[:40]}... */'

    # ------------------------------------------------------------------
    # 默认回退：列出所有已连接的输入
    # ------------------------------------------------------------------
    inputs = []
    for pin in node.get('pins', []):
        pin_name = pin.get('PinName', '')
        direction = pin.get('Direction', '')
        if direction == 'EGPD_Input' or pin_name in ('A', 'B', 'Alpha', 'Input', 'InputPin',
                                                      'LightValueInput', 'Fraction', 'Base', 'Exponent',
                                                      'SwitchValue', 'Default'):
            linked = pin.get('LinkedTo', [])
            if linked:
                val = build_expression(linked[0], nodes, visited.copy())
            else:
                val = pin.get('DefaultValue', 'None')
                if val:
                    val = f'Constant({val})'
                else:
                    val = 'None'
            inputs.append(f'{pin_name}={val}')

    return f'{expr_type}({", ".join(inputs)})'


def collect_named_reroutes(nodes):
    """收集所有 NamedRerouteDeclaration 为顶部变量声明"""
    lines = []
    for node_id, node in nodes.items():
        if node.get('expr_type') == 'MaterialExpressionNamedRerouteDeclaration':
            name = node['properties'].get('Name', node_id)
            expr = build_expression(node_id, nodes, set(), inline_reroutes=True)
            lines.append(f'{name} = {expr}')
    return lines


def generate_pseudo_code(nodes):
    """从 Root 节点出发，生成完整伪代码"""
    # 查找 Root
    root_id = None
    for nid, node in nodes.items():
        if 'Root' in nid:
            root_id = nid
            break
    if not root_id:
        return '/* 未找到 Root 节点 */'

    root = nodes[root_id]
    mat_name = 'UnknownMaterial'
    mat_prop = root.get('properties', {}).get('Material', '')
    m = re.search(r"'([^']+)'", mat_prop)
    if m:
        mat_name = m.group(1).split('.')[-1]

    from datetime import datetime
    lines = []
    lines.append(f'================================================================================')
    lines.append(f'{mat_name} 材质节点运算伪代码')
    lines.append(f'源文件: {mat_name}.txt')
    lines.append(f'生成日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'================================================================================')
    lines.append('')

    # NamedReroute 声明
    reroute_lines = collect_named_reroutes(nodes)
    if reroute_lines:
        lines.append('// NamedReroute Declarations')
        for rl in reroute_lines:
            lines.append(rl)
        lines.append('')

    # 材质输出赋值
    lines.append('// Material Outputs')
    for pin in root.get('pins', []):
        pin_name = pin.get('PinName', '')
        linked = pin.get('LinkedTo', [])
        if not linked:
            continue

        prop_name = translate_pin_name(pin_name)
        target = linked[0]
        expr = build_expression(target, nodes, set())
        lines.append(f'MaterialOutput.{prop_name} = {expr}')

    return '\n'.join(lines)


# =============================================================================
# 交互逻辑
# =============================================================================

def find_txt_files():
    """查找当前工作目录下所有 .txt 文件"""
    return sorted(glob.glob('*.txt'))


def select_file(files):
    """交互式选择文件，显示文件大小"""
    if not files:
        print('[错误] 当前目录下没有找到 .txt 文件。')
        return None

    print('\n' + '=' * 60)
    print('找到以下 .txt 文件:')
    print('=' * 60)

    for i, filepath in enumerate(files, start=1):
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        size_kb = file_size / 1024
        print(f'  [{i}] {filename} ({size_kb:.1f} KB)')

    if len(files) > 9:
        print(f'\n提示: 共有 {len(files)} 个文件，请输入对应的编号')

    while True:
        try:
            choice = input(f'\n请输入要处理的文件编号 [1-{len(files)}]: ').strip()
            if not choice:
                print('请输入编号')
                continue
            idx = int(choice)
            if 1 <= idx <= len(files):
                return files[idx - 1]
            else:
                print(f'编号超出范围，请输入 1 到 {len(files)} 之间的数字')
        except ValueError:
            print('输入无效，请输入数字编号')
        except KeyboardInterrupt:
            print('\n已取消')
            return None


def check_overwrite(output_path):
    """检查输出文件是否存在并询问是否覆盖"""
    if os.path.exists(output_path):
        print(f'\n文件已存在: {os.path.basename(output_path)}')
        while True:
            ans = input('是否覆盖？(y/n): ').strip().lower()
            if ans in ('y', 'yes', '是'):
                return True
            elif ans in ('n', 'no', '否', ''):
                return False
            else:
                print('请输入 y 或 n')
    return True


# =============================================================================
# 主入口
# =============================================================================

def main():
    files = find_txt_files()
    filepath = select_file(files)
    if not filepath:
        sys.exit(1)

    # 检测文件是否符合 UE 材质复制文本格式
    print(f'\n正在检测文件格式: {os.path.basename(filepath)} ...')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = []
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
        sample = ''.join(lines)
    except Exception as e:
        print(f'[错误] 读取文件失败: {e}')
        sys.exit(1)

    if 'Begin Object' not in sample and 'CustomProperties' not in sample:
        print('[错误] 文件不符合 UE 材质复制文本格式。')
        print('       请确保文件是从 UE 材质编辑器复制粘贴生成的文本。')
        sys.exit(1)
    print('文件格式检测通过。')
    # 生成输出文件名
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_path = f'{base_name}_material_node_pseudocode.txt'

    if not check_overwrite(output_path):
        print('操作已取消')
        sys.exit(0)

    print(f'\n正在解析: {os.path.basename(filepath)} ...')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f'[错误] 读取文件失败: {e}')
        sys.exit(1)

    nodes = parse_nodes(text)
    if not nodes:
        print('[错误] 未能解析出任何节点，请检查文件是否为 UE 材质复制文本。')
        sys.exit(1)

    pseudo_code = generate_pseudo_code(nodes)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pseudo_code)
        print('\n' + '=' * 60)
        print('完成！')
        print(f'伪代码已保存到: {output_path}')
        print('=' * 60)
    except Exception as e:
        print(f'[错误] 写入文件失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()