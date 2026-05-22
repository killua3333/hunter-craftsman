# 每周学习报告 2026-W20

- 处理反馈：4 条
- 已更新：`prompts/specialist_learnings.md`
- 备份：`prompts/specialist_learnings.md.bak`

## 原始模型输出（含分隔符前正文）

# Agent B 反馈归纳

## 近期教训与填写范例

### 重复出现的问题模式

1. **必填字段遗漏**：`core_logic.persistence`、`ui_layout.navigation`、`store.privacy_url`、`branding.primary_color` 必须全部填写，不可省略。Agent B 会直接拒绝缺少这些字段的机会单。

2. **core_logic 描述过于笼统**：仅写“持久化 UserDefaults”不够，必须说明存储的数据结构（键名、值类型、编码方式）。例如：`键 'history' 存储 JSON 编码的数组，每个元素包含表达式和结果`。

3. **ui_layout 缺少布局细节**：仅写 `navigation: stack` 不够，必须描述屏幕内的具体布局（如 VStack 包含显示区域和按钮网格，按钮包括哪些）。

4. **features 缺少子功能定义**：如果 feature 包含“历史”等交互元素，必须定义其交互行为（点击回填、清空按钮等）。

5. **核心逻辑未定义完整**：对于计算器等工具类 App，必须定义输入状态、支持的运算符、运算优先级、错误处理（除以零、溢出）。

### 好/坏对照范例

**坏范例（core_logic）**：
```json
"core_logic": {
  "persistence": "UserDefaults",
  "description": "保存用户输入的历史记录"
}
```
→ 缺少存储结构、键名、值类型，Agent B 无法实现。

**好范例（core_logic）**：
```json
"core_logic": {
  "persistence": "UserDefaults",
  "description": "使用 UserDefaults 键 'history' 存储 JSON 编码的数组，每个元素包含 {expression: String, result: String}；支持 +、-、×、÷ 四则运算，先乘除后加减；除以零显示 'Error'，溢出显示 'Overflow'"
}
```

**坏范例（ui_layout）**：
```json
"ui_layout": {
  "navigation": "stack",
  "screens": ["计算器主屏"]
}
```
→ 缺少布局细节，Agent B 无法确定按钮排列。

**好范例（ui_layout）**：
```json
"ui_layout": {
  "navigation": "stack",
  "screens": [
    "主屏：VStack 包含顶部显示区域（Text，显示输入和结果），下方 LazyVGrid 按钮网格（4列），按钮包括 0-9、+、-、×、÷、=、C、AC、小数点"
  ]
}
```

### 规则总结（给 Agent A 下次写机会单时用）

1. **必填检查清单**：每次输出前检查 `core_logic.persistence`、`ui_layout.navigation`、`store.privacy_url`、`branding.primary_color` 是否全部填写。

2. **core_logic 三要素**：存储方式 + 存储结构（键名/值类型） + 业务逻辑（输入状态、运算符、优先级、错误处理）。

3. **ui_layout 两层次**：导航类型 + 每屏的布局细节（使用 VStack/HStack/LazyVGrid 等组件描述）。

4. **features 完整性**：每个 feature 的 items 必须定义交互行为（点击、输入、清空等）。

5. **错误处理**：对于计算、输入类 App，必须说明边界情况处理（除以零、溢出、空输入等）。

---
