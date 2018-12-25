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
 
schedule:                           
  trigger: inteval                  #周期执行
  minutes: 5                        #每5分钟执行

```

## 运行

### 启动web服务

```cmd
python3 app.py
```

### 直接执行下载任务

```cmd
python3 run.py
```


## API

### 认证

使用Http Basic Auth,即用户名密码


### 下载任务映射配置

#### 查询所有映射

- URL: /mapper
- 方法: GET

##### 例子

```cmd
curl -u user:pass host:port/mapper
```

#### 添加下载任务的路径映射

- URL: /mapper  
- 方法: PUT
- 参数(json类型传递)：
  - localdir(str): 必选，本地目录
  - basedir(str):  必选，ftp服务器的起始目录
  - remotedir(str): 必选，想要进行递归下载的远程目录
  - processeddir(str): 可选，下载完的文件会被移动到这个目录，如果不填，则使用配置文件的配置
  - regex(str): 只下载文件名符合regex正则表达式的文件，如果不填，则使用配置文件的配置
  - force_create(bool): 如果不存在对应的本地文件，是否新建。默认为False
  
##### 例子

```cmd
curl -u user:pass -H 'Content-Type:Application/json' -XPUT host:port/mapper -d {"localdir":"c:\\local", "basedir":"vendor1", "remotedir":"download1"}
```

#### 删除下载任务路径映射

- url: /mapper/ID, id可以通过get方法得到
- 方法: DELETE


##### 例子

```cmd
curl -u user:pass -XDELETE host:port/mapper/5
```

### 下载任务

#### 执行下载任务

- URL: /job
- 方法: PUT

##### 例子

```cmd
curl -u user:pass -XPUT host:port/job
```

该方法返回一个异步执行的任务id

#### 查询任务结果

- URL: /job/TASKID
- 方法: GET

##### 例子

```cmd
curl -u user:pass host:port/job/xxx-xxx-xxx
```

如果任务执行完毕，返回任务结果


### 历史记录

#### 查询所有下载文件的历史记录

- URL: /history
- 方法: GET

##### 例子

```cmd
curl -u user:pass host:port/history
```
