Composite Repair Strength Analysis V2.2.0 — Abaqus/CAE 2024 / Python 3.10.5

使用顺序：
1. 打开插件，填写模型与修理参数。
2. 选择材料JSON并点击“加载材料参数”。
3. 创建模型；斜接式还需“划分网格并建立分析”。
4. 设置位移、Job、CPU和分析时间。
5. 提交普通计算或自动求剩余强度。
6. 自动计算完成后结果会直接写入结果表。

详细说明见 docs/插件使用说明书.docx。
材料参数快速说明见 material/材料参数JSON快速填写说明.txt。

Python 3 迁移说明见项目根目录 PYTHON3_MIGRATION_2024.md。
旧使用说明书中的 2021/2022 版本信息属于历史版本；当前目标为 2024。
