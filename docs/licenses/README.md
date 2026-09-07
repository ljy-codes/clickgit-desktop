# 第三方许可证

此目录是 ClickGit 发布包第三方许可证清单和许可证原文的治理入口。

Windows 清单必须覆盖 Python、PySide6/Qt、Shiboken6、PortableGit、Git
Credential Manager 以及 PortableGit 中随包分发的依赖。macOS 清单必须覆盖
应用包内的 Python、PySide6/Qt 和 Shiboken6。每次升级依赖或调整打包内容后，
都必须根据实际产物重新生成清单并收集适用的许可证、版权声明和第三方通知，
不得仅沿用旧版本声明。

`distribution` 保存随 Windows 和 macOS 包分发的许可证原文、Qt/PySide6/
Shiboken6 通知与源码提供说明。`LICENSE-MANIFEST.json` 固定依赖版本、文件
清单和 SHA-256。许可证文本统一将 CRLF/CR 换行规范化为 LF 后计算摘要，
保证 Windows 与 macOS 检出结果一致；`scripts/verify_licenses.py` 在构建前
核对实际 Python、PySide6、PyInstaller、PortableGit 版本，并在打包后再次
核对复制结果。

任何版本、文件、摘要或包内材料不匹配时，构建必须失败。升级依赖时必须重新
审查实际模块、更新原文与通知并重算摘要。自动校验只证明已声明材料一致，
不能替代针对具体发布方式的法律审查。
