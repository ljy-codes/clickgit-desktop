# 第三方许可证

此目录是 ClickGit 发布包第三方许可证清单和许可证原文的治理入口。

Windows 清单必须覆盖 Python、PySide6/Qt、Shiboken6、PortableGit、Git
Credential Manager 以及 PortableGit 中随包分发的依赖。macOS 清单必须覆盖
应用包内的 Python、PySide6/Qt 和 Shiboken6。每次升级依赖或调整打包内容后，
都必须根据实际产物重新生成清单并收集适用的许可证、版权声明和第三方通知，
不得仅沿用旧版本声明。

当前建立目录不代表现有最终安装包已经完成 Qt/PySide6 开源分发合规验证。
后续正式发布前必须检查 Windows 和 macOS 的实际安装包及归档文件，确认适用
的 LGPL/GPL 许可证文本、Qt 通知、源码提供信息及其他必要材料已随包分发。
任何材料缺失或验证未完成时，必须阻断发布。
