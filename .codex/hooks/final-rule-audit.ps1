$repo = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repo)) {
    exit 0
}

$status = git -C $repo status --short 2>$null
if ($LASTEXITCODE -ne 0 -or $null -eq $status -or [string]::IsNullOrWhiteSpace(($status -join "`n"))) {
    exit 0
}

[Console]::Out.WriteLine(@'
[final-rule-audit] 检测到当前仓库存在未提交改动。最终回复前必须完成：
1. 重新读取适用规则：用户级规则、项目根规则、当前子项目规则、目录级规则。
2. 审计所有已修改文件是否违反规则、范围约束或项目约定。
3. 针对本次修改运行最小相关验证；无法运行时明确说明 not verified。
4. 发现违反规则时先修复，再回复用户。

已修改文件：
'@)

foreach ($line in $status) {
    [Console]::Out.WriteLine($line)
}

exit 0
