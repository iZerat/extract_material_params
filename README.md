# UE Analyze Material Node Tool

虚幻引擎材质参数提取与报告生成工具集。在虚幻引擎材质编辑器中全选所有节点（Ctrl+A）并复制（Ctrl+C），将剪贴板中的纯文本输入到本工具，即可生成结构化的参数统计报告或节点运算关系伪代码。

> ⚠️ 虚幻材质资产本身是 `.uasset` 二进制文件，无法直接读取，须通过虚幻引擎编辑器复制节点获取纯文本内容。
> 虽然能在编辑器内把材质资产导出为 `.COPY`或 `.T3D` 的纯文本文件，但本工具集还是基于剪贴板的内容进行分析提取，与 `.COPY` `.T3D` 文件并不兼容。

👉 **[GitHub Pages 在线预览](https://izerat.github.io/UE_analyze_material_node/UE_extract_material_node_params.html)**（仅支持参数统计功能，节点运算关系提取需要python脚本）

## 功能特性

### 1. 参数提取与报告生成
- **参数提取**：自动识别 Scalar、Vector4、Texture2D、StaticSwitch、Curve、CollectionParameter 等材质参数类型
- **分组展示**：按材质参数分组（Group）组织，未分组参数单独归类
- **参数统计**：统计各类型参数数量
- **剪贴板读取**：支持直接从剪贴板粘贴虚幻材质文本并生成报告（需通过本地服务器访问）
- **一键复制**：支持复制参数名、分组名到剪贴板
- **目录导航**：左侧目录栏支持点击跳转，自动高亮当前位置
- **中英双语**：支持中文 / English 一键切换

### 2. 节点运算关系提取
- **节点图解析**：从 UE 材质复制文本中解析所有 MaterialGraphNode 节点
- **运算关系追踪**：递归追踪节点输入连接，构建完整的运算树
- **分支节点处理**：正确处理 StaticSwitchParameter、StaticSwitch、Switch、Lerp、ShadingPathSwitch 等分支/选择节点
- **材质函数展开**：完整展开 MaterialFunctionCall 的输入输出关系
- **伪代码生成**：将节点连接关系转换为人类可读的伪代码，便于分析材质计算逻辑
- **命名重路由声明节点支持**：将 NamedRerouteDeclaration 提取为变量声明，使用时以变量名引用

## 文件说明

| 文件 | 说明 | 对应功能 |
| --- | --- | --- |
| `UE_extract_material_node_params.html` | 浏览器打开即可使用，纯前端实现，无需后端。提供参数统计报告的可视化界面 | 参数提取与报告生成 |
| `start_server.bat` | Windows 批处理脚本，一键启动本地 HTTP 服务器（解决浏览器剪贴板权限问题） | 参数提取与报告生成 |
| `UE_extract_material_node_params.py` | Python 脚本版，支持批量处理由虚幻材质节点文本保存的 `.txt` 文件，输出 TXT / Markdown / HTML 三种格式 | 参数提取与报告生成 |
| `UE_extract_material_node_math.py` | 后续开发的拓展功能，从同一来源的 UE 材质复制文本中提取节点运算关系，输出为伪代码（`.txt` 格式），便于分析材质计算逻辑 | 节点运算关系提取 |

## 使用方法

### 参数提取与报告生成

#### 方法一：浏览器直接打开

1. 双击打开 `UE_extract_material_node_params.html`
2. 在虚幻引擎 **材质编辑器** 中，按 **Ctrl+A** 全选所有节点，再按 **Ctrl+C** 复制
3. 将剪贴板中的文本粘贴到右侧「操作面板」的输入框中
4. 点击 **从输入栏中重新生成**，即可查看报告

> 直接双击打开（ `file://` 协议）时，「粘贴并重新生成」按钮因浏览器安全限制无法自动读取剪贴板，需要在弹窗里允许浏览器查看剪切板的内容。

#### 方法二：本地服务器启动（解锁剪贴板自动读取）

1. 确保已安装 Python 3
2. 双击运行 `start_server.bat`
3. 脚本会自动打开浏览器访问 `http://localhost:8080/UE_extract_material_node_params.html`
4. 点击 **粘贴并重新生成**，浏览器可能会询问剪贴板权限，首次允许剪贴板权限后，后续不再弹窗

> 终端窗口即为服务器进程，使用期间请勿关闭。

#### 方法三：Python 脚本批量处理

适用于需要批量处理历史保存的节点文本文件，生成参数统计报告。

```bash
# 1. 在虚幻材质编辑器中复制节点文本（Ctrl+A → Ctrl+C）
# 2. 粘贴到新建的空白 .txt 文件中保存
# 3. 将该 .txt 文件放入脚本同级目录

python UE_extract_material_node_params.py

# 按提示选择文件 → 检测目标文件是否符合格式 → 选择输出格式（TXT / Markdown / HTML）→ 确认覆盖 →完成
```

脚本会自动扫描当前目录下的 `.txt` 文件，提取参数后输出到同级目录，文件名格式为：

| 输出格式 | 文件名模板 |
| --- | --- |
| TXT | `{材质名}_material_parameter_statistical_report.txt` |
| Markdown | `{材质名}_material_parameter_statistical_report.md` |
| HTML | `{材质名}_material_parameter_statistical_report.html` |

> 若无法从文本中识别材质名称，则使用原 `.txt` 文件名（不含扩展名）作为前缀。

---

### 节点运算关系伪代码提取

适用于需要分析材质内部计算逻辑、排查节点连接问题、或文档化材质运算流程的场景。

#### Python 脚本批量处理

```bash
# 1. 在虚幻材质编辑器中复制节点文本（Ctrl+A → Ctrl+C）
# 2. 粘贴到新建的空白 .txt 文件中保存
# 3. 将该 .txt 文件放入脚本同级目录

python UE_extract_material_node_math.py

# 按提示选择文件 → 检测目标文件是否符合格式 → 确认覆盖 → 完成
```

脚本会自动扫描当前目录下的 `.txt` 文件，解析节点运算关系后输出 `{base_name}_material_node_pseudocode.txt`，包含：
- 命名重路由声明节点
- 材质输出赋值（BaseColor、Metallic、Roughness 等）
- 完整的运算树（含分支节点、材质函数调用）

## 效果展示

### 参数提取网页截图展示
![UE_extract_material_node.png](https://cdn.jsdelivr.net/gh/iZerat/resource@master/UE_extract_material_node.png)

### 节点运算伪代码示例
```text
// Material: M_Mannequin

// NamedReroute Declarations
Color = Lerp(TextureSampleParameter2D("Base Texture", ...), ...)

// Material Outputs
MaterialOutput.BaseColor = Switch(
    SwitchValue=Constant(0.0),
    Default=Constant(0.0),
    Input0=StaticSwitch(
        True=StaticSwitchParameter("UseLogo", True=Color, False=float3(0,0,0), Default=false),
        False=float3(0, 0, 0)
    ),
    Input1=float2(0, 0)
)
MaterialOutput.Metallic = Lerp(Metallic, ScalarParameter("MetalPaintMetallic", Default=1.0), MetalPaintMask)
...
```

## 技术说明

两个脚本处理同一来源（UE 材质编辑器复制出的纯文本），但关注点不同：

| 脚本 | 关注点 | 输出 |
| --- | --- | --- |
| `UE_extract_material_node_params.py` | 材质**参数**（ScalarParameter、VectorParameter、TextureSampleParameter 等） | 结构化统计报告 |
| `UE_extract_material_node_math.py` | 材质**运算关系**（节点连接、分支选择、函数调用） | 伪代码 |

可根据需求单独或组合使用。
