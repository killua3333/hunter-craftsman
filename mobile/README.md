# ai帮我赚钱 Mobile

由三个 Agent 协作的 Android 移动工作台：猎手搜索真实需求，工匠生成和测试 App，管理 Agent 负责上架与盈利监控。正式模式不包含演示数据；用户粘贴自己的 DeepSeek API Key，由固定供应商后台验证并驱动完整流程。

后端接口、安全隔离和计费要求见 [BACKEND_API_README.md](BACKEND_API_README.md)。

## 本地运行

```powershell
npm install
npm run dev
```

## 校验 Web 与业务流程

```powershell
npm run verify
```

该命令会运行 store、组件和页面流程测试，并继续执行 TypeScript 检查与生产构建。

## 构建 Android 调试安装包

```powershell
npm run cap:sync
cd android
.\gradlew.bat testDebugUnitTest assembleDebug
```

APK 输出：`android/app/build/outputs/apk/debug/app-debug.apk`

可直接侧载的测试包：`release/ai-help-me-make-money-0.3.0-debug.apk`。它保留应用包名 `com.huntercraftsman.mobile`，可覆盖安装旧版本；使用 Android 调试证书签名，仅用于接口联调和验收。

正式客户包必须在构建时设置固定 HTTPS 后台：

```powershell
$env:VITE_BACKEND_URL = "https://api.example.com"
npm run cap:sync
```

## 页面

- 总览：用一张卡片直接展示净利润、累计收入与生产成本
- 猎手：搜索竞品评论与真实用户需求
- 需求：查看候选评分、证据、痛点与建议功能
- 工匠：查看 App 生成、质量检查和安装包进度
- 管理：粘贴 DeepSeek API Key、连接固定后台，并查看真实上架状态与收益
