# 第三方依赖说明

自有代码采用 MIT；依赖保留各自许可，图片、视频不受 MIT 自动授权。

| 依赖 | 本次版本 | 对应许可与源码 |
|---|---|---|
| Python | 3.11.5 | PSF License；`licenses/Python-3.11.5-LICENSE.txt`；[源码](https://www.python.org/downloads/release/python-3115/) |
| PySide6 Essentials/Addons、Shiboken6 | 6.8.3 | LGPL-3.0 路径；`licenses/pyside-setup-v6.8.3`；[源码](https://github.com/qtproject/pyside-pyside-setup/tree/v6.8.3) |
| QtCore/Gui/Widgets/Network | 6.8.3 | LGPL-3.0；`licenses/qtbase-v6.8.3`；[源码](https://github.com/qt/qtbase/tree/v6.8.3) |
| QtMultimedia | 6.8.3 | LGPL-3.0；`licenses/qtmultimedia-v6.8.3`；[源码](https://github.com/qt/qtmultimedia/tree/v6.8.3) |
| FFmpeg | 7.1 | LGPL-2.1-or-later 及内置组件各自许可；`licenses/FFmpeg-7.1` 与 QtMultimedia 的 attribution；[源码](https://github.com/FFmpeg/FFmpeg/tree/n7.1) |
| PyInstaller 引导程序 | 6.16.0 | GPL-2.0-or-later WITH Bootloader-exception；`licenses/pyinstaller`；[源码](https://github.com/pyinstaller/pyinstaller/tree/v6.16.0) |
| OpenSSL（被运行库收集） | 3.0.9 / 3.6.4 | Apache-2.0；`licenses/OpenSSL`；[3.0.9](https://github.com/openssl/openssl/tree/openssl-3.0.9)、[3.6.4](https://github.com/openssl/openssl/tree/openssl-3.6.4) |

Qt/PySide6 are Copyright The Qt Company Ltd. and other contributors. FFmpeg is Copyright the FFmpeg developers. OpenSSL is Copyright The OpenSSL Project Authors and other contributors. 具体第三方版权与许可原文保存在 licenses；来源清单为 `licenses/UPSTREAM_SOURCES.json`。其中含备选许可文本，不表示选择商业许可或将第三方内容重新许可为 MIT。

应用为 onedir 动态库包，保留 Qt、FFmpeg 等 DLL 可替换；不禁止为调试这些 LGPL 组件的修改而进行逆向工程。对应应用源码、固定依赖和构建步骤见 README；依赖对应源码见上表，按其上游构建说明重建并替换兼容动态库。二进制包必须保留 licenses、LICENSE 和本文件。

PyInstaller 会收集部分 QtNetwork/SSL 模块，应用本身不调用网络功能。删除未使用的 SVG/额外图像格式插件及 Mesa 软件 OpenGL，保留 JPEG 和多媒体插件。Python 的 libffi 等版权说明见 Python LICENSE；Windows C/C++ 运行库保留其原许可。

重新构建、更换版本或依赖收集路径后，应重新核对实际 DLL 及许可。未经确认不将用户照片、数据库、日志或本次提供的素材公开发布。
