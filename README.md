# Abaqus plugins

面向 **Abaqus/CAE 2024 / Python 3.10.5** 的复合材料修理分析插件。

| 目录 | 版本 | 用途 |
| --- | --- | --- |
| `Composite_Repair_Strength_Analysis` | 2.2.0 | 双面贴补、阶梯及斜接修理建模，计算控制与结果报告 |
| `ImpactRepairCAI` | 0.4.0 | 冲击后压缩及贴补修理后压缩流程 |

将两个插件文件夹放入 Abaqus 插件搜索目录，保存工作并重启 CAE。已配置 `plugin_central_dir` 时可将本仓库克隆至该目录。使用 Python 3 的 2024 启动器，避免 PATH 仍指向旧版。

菜单入口：`Composite Repair Strength Analysis V2.2.0`、`Impact Repair CAI 2024`。

迁移处理了脚本执行与模块重载、中文界面和路径、UTF-8 JSON/CSV、原生 Unicode 字符区域编码及 Tie 参数。详见 [迁移记录](PYTHON3_MIGRATION_2024.md)。

本次迁移验证：40 项单元测试通过；原生 GUI 对话框及注册、中文 ODB 读取通过；三类修理小模型完成建模和 INP 写出。尚未执行迁移后的完整求解、VUMAT 编译及 CAI 状态导入验证。2022 的 ODB 升级不能代替 Explicit 状态库转换，CAI 输入需使用 2024 生成的完整源状态。

源码库不包含仿真结果、历史安装包、二进制手册或本机验证日志。子目录文档提及的历史验证产物保留在原工作区。

## 回归测试

在仓库根目录使用 Abaqus 2024 启动器：

```text
abaqus python -m unittest discover -s Composite_Repair_Strength_Analysis/tests -p test_python3_compat.py -v
abaqus python -m unittest discover -s ImpactRepairCAI/tests -v
```
