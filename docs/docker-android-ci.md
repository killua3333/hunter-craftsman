# Android CI / Docker 构建

Windows 无本机 Android SDK 时，通过 **Docker builder 镜像**在容器内跑 Gradle，产出真实 APK/AAB 与可选冒烟测试。

## 两种模式

| 模式 | 镜像 tag | Entrypoint | 用途 |
|------|----------|------------|------|
| **Builder** | `hunter-craftsman/android-builder` | `/opt/builder/gradle-run.sh` | 宿主机 `docker run` 单次编译 / smoke |
| **Serve**（可选） | 自定义 | `craftsman serve` | Linux 容器内长期跑 Craftsman API |

本仓库默认 Dockerfile 为 **Builder** 模式（含 SDK + emulator 组件）。

## 构建 Builder 镜像

在仓库根目录执行：

```bash
cd hunter-craftsman
docker build -f docker/Dockerfile.android-ci -t hunter-craftsman/android-builder .
```

## 宿主机配置（Windows + Docker Desktop）

[`craftsman/.env`](../craftsman/.env)：

```env
ANDROID_BUILD_BACKEND=auto
DOCKER_ANDROID_IMAGE=hunter-craftsman/android-builder
SKIP_GRADLE_BUILD=false
```

- `auto`：Docker 可用 → Agent B 用 `assembleDebug` 验证；Agent C 用 `bundleRelease`
- `docker`：强制 Docker
- `local`：本机 gradlew（需 JDK + SDK）

手动试编译：

```powershell
docker run --rm -v "${PWD}/craftsman/workspace/RUN_ID/project:/workspace/project" `
  -w /workspace/project hunter-craftsman/android-builder assembleDebug
```

## 冒烟测试（可选）

```env
ANDROID_SMOKE_TEST=auto
ANDROID_SMOKE_TIMEOUT_SECONDS=600
ANDROID_SMOKE_MAX_ROUNDS=2
```

容器内：`gradle-run.sh smoke {package_id}` → AVD + `adb install` + monkey 50。

**设备验收边界**：Linux 主机存在 `/dev/kvm` 时，系统会将 KVM 映射到 smoke 容器并运行模拟器。Windows Docker Desktop 通常无法提供该设备，因此 `auto` 会记录 `smoke_skipped`。原生编译成功仍会保留，但没有设备启动证据的产物不会通过发布质量门槛。

Builder 镜像、Android 模板和 AGP 当前统一使用 API 34，避免构建时临时下载其他 SDK。修改 SDK 版本后必须同步更新镜像与模板并重新验证。

## 何时使用

- 需要 **verification=verified** 而非 demo
- Agent C 真 AAB 不依赖 Windows 本机 Gradle
- CI/Linux 批量 autopilot

Hunter 在宿主机运行，`CRAFTSMAN_BASE_URL` 指向 Craftsman API 即可。

## Release 构建说明

- Agent C 的 release 模板默认 **`isMinifyEnabled = false`**（R8 混淆关闭），便于调试与 smoke 测试。
- 冒烟测试使用 **debug APK**（`assembleDebug`）；Agent C 真上架走 `bundleRelease` AAB。
