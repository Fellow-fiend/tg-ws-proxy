[app]
title = TG WS Proxy
package.name = tgwsproxy
package.domain = org.flowseal
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = .git,__pycache__,packaging
version = 0.1.0
requirements = python3,kivy,cryptography
orientation = portrait
fullscreen = 0
android.api = 34
android.minapi = 21
android.build_tools_version = 34.0.0
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
