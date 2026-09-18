# Third-party notices

本文件用于记录来源与许可证边界，不构成对任何第三方材料授权状态的保证。

## OCS / ocsjs

- 上游项目：https://github.com/ocsjs/ocsjs
- 官方文档：https://docs.ocsjs.com/
- 上游许可证：MIT License
- 本仓库使用方式：`OCS刷题脚本.js` 是修改后的编译用户脚本，增加本地 autoSolve 接口、安全保存和字体解码调用。

分发修改版时必须保留原作者、MIT 许可证声明和上游来源，不得暗示本项目是 OCS 官方版本或获得官方背书。

## Chaoxing font-confusion reference data

- 参考项目：https://github.com/TellMeYourWish/chaoxing_solution_of_font_confusion
- 涉及文件：
  - `autosolve/assets/chaoxing_font/HanSansCN_CmapTables.pkl`
  - `autosolve/assets/chaoxing_font/HanSansCN_glyfHashedTables.pkl`
- 用途：根据原始 `glyf` 字节指纹将页面子集字体映射回 Unicode 字符。

截至本次整理时，参考仓库页面未显示明确的许可证文件。代码或数据公开可见不等于当然取得复制、修改或再分发授权。发布者应在公开发布前联系权利人确认授权，或移除上述文件并以自己有权使用的字体/字形数据重新生成兼容资产。

## Python dependencies

Flask、fontTools、pytest、Playwright 由各自权利人按各自许可证提供。`requirements.txt` 仅声明依赖，不改变其许可证。

## Service names and trademarks

OCS、超星学习通、DeepSeek、ScriptCat、Tampermonkey 及其他名称可能是其各自所有者的商标。本仓库仅为兼容性说明而提及，不表示关联、授权或背书。
