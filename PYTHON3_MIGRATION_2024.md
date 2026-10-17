# Abaqus 2024 / Python 3 迁移记录

日期：2026-10-17。目标环境：本机 `D:\ABAQUS2024`，Python 3.10.5。

本次更新两个插件：`Composite_Repair_Strength_Analysis` V2.2.0、`ImpactRepairCAI` 0.4.0。直接修改工作区源码，旧源码备份在 `.codex_checks/python3_2024/source_before_migration.zip`，可审阅差异在同目录 `migration.diff`。历史 ZIP、求解结果和 VUMAT 源码保留。

## 修改内容

- 用 `compile` / `exec` 替换 `execfile`，保留建模、边界、求解和后处理脚本共享的全局命名空间。
- 模块重载显式使用 `importlib.reload`；文件选择器用 `getattr` 代替动态赋值语句。
- 中文界面使用 Python 3 `str`，去除传给 GUI 的 GBK 字节串；ODB/CAE 接口路径也保持 `str`，支持 PathLike 输入。
- 本机原生 GUI/ODB 接口在非 ASCII 字符串转换时出现 `Failed to encode Unicode object to locale`。在 Windows 的非 ASCII 文本/路径进入接口前，将当前进程的 `LC_CTYPE` 设置为 `.UTF8`；不更改系统设置或 `LC_NUMERIC`。已实际验证中文界面和含中文、空格的 ODB 路径。
- CSV 使用文本模式及 `newline=''`；界面汇总 CSV 使用 UTF-8 BOM，保留 Excel 中文显示。材料/结果 JSON 显式按 UTF-8（允许 BOM）读取，结果报告按 UTF-8 写入。
- Tie 接口更新为 Abaqus 2024 的 `main` / `secondary` 参数。
- CAI 源版本检查改为 2024，同时核对 STA 中可识别的 Explicit 求解版本。只升级 ODB 不能转换同名的二进制状态库，2022 源状态应在 2024 重新生成并重新执行输入检查。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| 两个插件共 28 个 Python 文件的 Python 3.10 语法检查 | 通过 |
| CAI 原有回归测试及新增迁移测试 | 35 项通过 |
| 原插件新增迁移测试：共享脚本命名空间、中文路径/界面文本、CSV、完整报告文件写出 | 5 项通过 |
| 原生 GUI Toolkit：两个对话框创建、菜单注册、CAI 模式和参数读取 | 通过 |
| 原生 odbAccess：两个路径函数分别读取 ASCII 和中文空格路径 | 4 项通过 |
| 双面贴补小模型：2292 节点 / 1572 单元 | CAE 建模及 INP 输出通过 |
| 阶梯修理小模型：4073 节点 / 4028 单元 | CAE 建模及 INP 输出通过 |
| 斜接修理小模型：82330 节点 / 69036 单元 | CAE 建模及 INP 输出通过 |

原迁移工作区的本机证据位于 `.codex_checks/python3_2024/`（未上传求解输入、日志及 ODB）：`composite_tests.log`、`cai_tests.log`、`gui_smoke.log`、`native_odb_probe.json`、`cae_smoke_results.json`，以及三个 `model_smoke_*.inp`。GUI 使用独立最小测试程序构造控件，未进行人工逐按钮视觉验收；该测试进程主动退出后的 IPC 断开日志不是建模/求解结果。

本次没有提交完整有限元求解，没有验证 VUMAT 编译链接，也没有以 2024 冲击源结果完成 CAI 状态导入和求解。此前 `ImpactRepairCAI/VALIDATION.md` 中的 2022 状态传递和强度相关检查是历史记录，不能作为 2024 的完整求解验证。测试目录中旧 `audit_v21*.py` 等是旧发布包的历史审计脚本，本次回归使用下述 unittest 命令。

## 安装和运行

1. 保存工作并关闭 Abaqus/CAE。
2. 将本仓库的两个插件文件夹放到 Abaqus 的插件搜索目录；本机已部署到 `D:\ABAQUS2024\plugins`。也可使用原迁移工作区的安装 ZIP。先保留原目录备份，不要仅覆盖 `.pyc`。
3. 使用 `D:\ABAQUS2024\Commands\abq2024.bat` 启动 2024，并重新打开插件。菜单分别为 `Composite Repair Strength Analysis V2.2.0` 和 `Impact Repair CAI 2024`。
4. 本机 PATH 中 `D:\SIMULIA\Commands\abaqus.bat` 仍指向旧 2022 启动器，本次未修改系统 PATH 或安装目录。执行命令时明确使用 2024 启动器。

项目根目录下可复查纯 Python 测试：

```powershell
& 'D:\ABAQUS2024\Commands\abq2024.bat' python -m unittest discover -s Composite_Repair_Strength_Analysis\tests -p test_python3_compat.py -v
& 'D:\ABAQUS2024\Commands\abq2024.bat' python -m unittest discover -s ImpactRepairCAI\tests -v
```

本次测试直接使用安装目录下的 `product\win_b64\code\bin\SMALauncher.exe`，不依赖旧 PATH；这不验证批处理中的编译器环境配置。

官方版本依据：[SIMULIA Abaqus Python 3 Update](https://3dswym.3dexperience.3ds.com/wiki/simulia-community/abaqus-python-3-update_Jh6mYnf4RwWRxe1OF4pxQw)。
