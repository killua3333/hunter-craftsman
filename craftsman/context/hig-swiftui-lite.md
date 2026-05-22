# SwiftUI HIG（工匠简化版）

- 最低 iOS 17；使用 `NavigationStack` 而非已废弃的 `NavigationView`。
- 列表用 `List`；纵向布局用 `VStack`；表单用 `Form`。
- 主入口：`@main struct AppNameApp: App { var body: some Scene { WindowGroup { ContentView() } } }`。
- 颜色使用 `Color` + hex 扩展；遵循系统动态字体 `.font(.body)`。
- 权限在 `Info.plist` 声明用途字符串（相机、定位等）。
- 持久化：`UserDefaults` 用 `@AppStorage`；`SwiftData` 用 `@Model`；`none` 仅内存 `@State`。
