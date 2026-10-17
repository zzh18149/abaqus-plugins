# GitHub 代码同步绑定

- 状态：启用。
- 授权：用户于 2026-10-17 指定本插件目录及以下 GitHub 仓库，要求同步本次 Python 3 迁移代码。
- 仓库：https://github.com/zzh18149/abaqus-plugins
- 远程：origin。
- 目标分支：main。
- 触发：Codex 完成此项目代码修改及适当验证后、最终回复前；不是后台监控服务。

## 范围

允许：`Composite_Repair_Strength_Analysis/` 和 `ImpactRepairCAI/` 下的实际源码、Fortran 源码、当前测试、材料配置、配置样例及简短说明；根目录 `README.md`、`PYTHON3_MIGRATION_2024.md`、`AGENTS.md`、`.gitignore`、`.gitattributes`；本规则文件；各插件发布清单 `manifest.sha256`。

排除：凭据、私钥、真实环境秘密、Python 缓存、安装包、仿真结果、二进制模型、求解日志、旧验证产物、历史备份和 `.codex_checks/`。`validation/`、`jobs/`、二进制使用手册不属于此次上传范围。不要为匹配此规则删除已有远端文件或重写历史。

## 验证命令

在仓库根目录，使用指向 Abaqus 2024 的启动命令执行：

```text
abaqus python -m unittest discover -s Composite_Repair_Strength_Analysis/tests -p test_python3_compat.py -v
abaqus python -m unittest discover -s ImpactRepairCAI/tests -v
```

语言和 I/O 修改至少执行以上测试；原生接口修改应运行对应 CAE/GUI 小模型验证。环境限制导致原生验证无法执行时，记录未验证范围，已有纯 Python 测试通过后允许同步源码，但不得宣称完整兼容性已验证。

精确暂存本任务文件；核对 origin 的 fetch/push URL、main 分支、已有提交及暂存区；获取远端最新状态后普通推送；禁止强推。推送后用远端 SHA 核实。认证或分支冲突时保留本地提交并报告。
