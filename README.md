# 漫画阅读器manga_reader

这是一个基于 FastAPI 的漫画阅读器后端应用。

这是一个由AI辅助完成的应用，用于个人练手。
A web software for reading comics, generated by AI support

## 功能特性

- 支持多个漫画库
- 支持 ZIP 和 RAR 压缩文件
- 提供 RESTful API 接口
- 支持漫画阅读和管理

## 安装说明

1. 克隆仓库：
   ```
   git clone https://github.com/yourusername/comic-reader.git
   cd comic-reader
   ```

2. 创建并激活虚拟环境：
   ```
   python -m venv venv
   source venv/bin/activate  # 在 Windows 上使用 venv\Scripts\activate
   ```

3. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

4. 运行应用：
   ```
   python run_app.py
   ```

5. 打开浏览器，访问 http://localhost:18081

## 使用说明

1. 打开浏览器，访问 http://localhost:18081 。

2. 在管理页面（http://localhost:18081/admin）添加漫画资料库。

   填入漫画资料库，漫画资料库根目录下的图片不会被加载出来。

   会加载的只有根目录下的文件夹名或者zip/rar压缩包并将其作为漫画书。

   所以根目录下面不应直接存在图片，请新建一个文件夹放进去。

3. 开始阅读您的漫画！

## 更新记录

1. 2024.09.06.v04 增加了后台清除缓存的按钮，当用户对资料库中的文件夹增删改查时，可以通过“刷新数据库和缓存”按钮来刷新；删除/重新添加数据库时也会清除缓存。
2. 2024.09.06.v03 提升了加载效率
3. 2024.09.06.v02 增加对7z支持。 
4. 2024.09.06. 修复bug 将base_path改为相对路径。 
5. 2024.09.05. 更改控件bar的位置和样式；在选择阅读模式是“瀑布式”或“翻页式”后记忆当前阅读样式

## 许可证

本项目采用 MIT 许可证。详情请见 [LICENSE](LICENSE) 文件。
