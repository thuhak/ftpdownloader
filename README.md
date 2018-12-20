# FTP(s) 订阅下载工具

> 为QDM需求单独设计

## 功能

订阅FTP的某几个文件夹，下载到本地特定文件夹


## 特性

- 订阅的文件夹以及映射关系放在数据库中
- 记录下载过的文件，不重复下载相同的文件
- 处理后的文件移动到特定的文件夹


## 配置

```yaml
database:                             
  host: 127.0.0.1                   #数据库地址 
  port: 3306                        #数据库端口
  db: qdm                           #数据库名称
  user: qdm                         #数据库用户
  password: password                #数据库密码

ftp:
  host: test.nioint.com             #ftp服务器地址
  timeout: 3                        #ftp连接超时
  tls: True                         #是否使用Ftps
  user: user                        #ftp用户
  password: password                #ftp密码
  default_regex: .+\.xls(x){0,1}$   #(可选参数)默认的搜索表达式，可以被数据库中的配置覆盖
  default_processed: _processed     #(可选参数)默认的处理过文件存放的文件夹后缀，可以被数据库中的配置覆盖

log:
  level: debug                      #日志级别
  path: /tmp/downloader.log         #日志存放路径

api:
  user: test                        #api用户名
  password: test                    #api密码
```
