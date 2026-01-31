# Soniva Backend

声韵 - AI声音社交应用后端API服务

## 技术栈

- **框架**: FastAPI
- **数据库**: MySQL + SQLAlchemy ORM
- **认证**: JWT (python-jose)
- **音频处理**: librosa
- **实时通讯**: WebSocket

## 项目结构

```
soniva-backend/
├── app/
│   ├── main.py                 # 应用入口
│   ├── config.py               # 配置管理
│   ├── database.py             # 数据库连接
│   ├── dependencies.py         # 依赖注入
│   ├── api/
│   │   └── api_v1/
│   │       ├── api.py          # 路由聚合
│   │       └── endpoints/      # API端点
│   │           ├── auth.py         # 认证
│   │           ├── voice_test.py   # 声音测试
│   │           ├── voice_card.py   # 声卡
│   │           ├── identify.py     # 识Ta
│   │           ├── chat_room.py    # 聊天室
│   │           ├── message.py      # 消息中心
│   │           ├── square.py       # 广场
│   │           └── user.py         # 用户
│   ├── models/                 # 数据模型
│   │   ├── user.py
│   │   ├── voice_test.py
│   │   ├── voice_card.py
│   │   ├── identify.py
│   │   ├── chat_room.py
│   │   ├── message.py
│   │   └── square.py
│   ├── services/               # 业务服务
│   │   └── voice_service.py    # 声音分析服务
│   └── utils/                  # 工具函数
│       ├── response.py         # 响应格式
│       └── security.py         # 安全工具
├── requirements.txt            # Python依赖
├── .env                        # 环境配置
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env` 文件并修改配置:

```bash
cp .env.example .env
```

主要配置项:
- `DATABASE_URL`: MySQL连接字符串
- `SECRET_KEY`: JWT密钥
- `LOCAL_STORAGE_PATH`: 文件存储路径

### 3. 初始化数据库

确保MySQL数据库 `soniva_db` 已创建，然后启动应用会自动创建表。

### 4. 启动服务

```bash
# 开发模式
python -m app.main

# 或使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 访问API文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 模块

### 认证模块 `/api/v1/auth`
- POST `/send-code` - 发送验证码
- POST `/register` - 用户注册
- POST `/login` - 用户登录
- POST `/refresh` - 刷新Token
- POST `/logout` - 退出登录

### 声音测试 `/api/v1/voice-test`
- POST `/upload` - 上传音频文件
- POST `/analyze` - AI声音分析
- GET `/history` - 测试历史
- GET `/result/{id}` - 获取结果详情
- DELETE `/result/{id}` - 删除结果

### 声卡 `/api/v1/voice-card`
- GET `/templates` - 获取模板列表
- POST `/generate` - 生成声卡
- GET `/my-cards` - 我的声卡
- GET `/{id}` - 声卡详情
- POST `/{id}/share` - 分享声卡
- DELETE `/{id}` - 删除声卡

### 识Ta `/api/v1/identify`
- POST `/upload` - 上传目标声音
- POST `/analyze` - 分析生成画像
- GET `/portraits` - 画像列表
- GET `/portrait/{id}` - 画像详情
- POST `/portrait/{id}/favorite` - 收藏画像
- DELETE `/portrait/{id}` - 删除画像

### 聊天室 `/api/v1/chat-room`
- POST `/create` - 创建房间
- GET `/list` - 房间列表
- GET `/{id}` - 房间详情
- POST `/{id}/join` - 加入房间
- POST `/{id}/leave` - 离开房间
- POST `/{id}/mic/request` - 申请上麦
- POST `/{id}/mic/approve/{request_id}` - 批准上麦
- POST `/{id}/mic/leave` - 下麦
- POST `/{id}/mic/mute/{seat}` - 静音
- POST `/{id}/close` - 关闭房间
- GET `/{id}/messages` - 消息历史
- WS `/ws/{id}` - WebSocket连接

### 消息中心 `/api/v1/message`
- GET `/conversations` - 会话列表
- GET `/conversation/{user_id}` - 获取/创建会话
- GET `/messages/{conversation_id}` - 消息列表
- POST `/send` - 发送私信
- GET `/comments` - 评论通知
- POST `/comments/read` - 标记已读
- GET `/notifications` - 系统通知
- POST `/notifications/read` - 标记已读
- GET `/unread-counts` - 未读数量

### 广场 `/api/v1/square`
- GET `/feed` - 动态列表
- POST `/post` - 发布动态
- GET `/post/{id}` - 动态详情
- DELETE `/post/{id}` - 删除动态
- POST `/post/{id}/like` - 点赞
- GET `/post/{id}/comments` - 评论列表
- POST `/post/{id}/comment` - 发表评论
- POST `/comment/{id}/like` - 评论点赞
- DELETE `/comment/{id}` - 删除评论
- POST `/post/{id}/favorite` - 收藏

### 用户 `/api/v1/user`
- GET `/profile` - 我的资料
- PUT `/profile` - 更新资料
- POST `/avatar` - 上传头像
- PUT `/password` - 修改密码
- PUT `/anonymous` - 匿名设置
- GET `/{id}` - 用户资料
- POST `/{id}/follow` - 关注/取关
- GET `/{id}/followers` - 粉丝列表
- GET `/{id}/following` - 关注列表
- GET `/me/favorites` - 我的收藏
- GET `/{id}/posts` - 用户动态

## 声音分析算法

基于 librosa 提取以下特征:
- 基频 F0 (音高)
- MFCC (梅尔频率倒谱系数)
- 频谱质心 (声音亮度)
- 频谱对比度
- 过零率 (气息感)
- RMS能量 (音量)
- 谐波比 (清晰度)
- 共振峰 (音色)

根据特征计算声音类型匹配度:
- 女声: 萝莉音、少女音、御姐音、女王音、软萌音、温柔音、甜美音、知性音、烟嗓音
- 男声: 正太音、少年音、青年音、大叔音、青攻音、青受音、奶狗音、狼狗音、播音音、烟嗓音

## 数据库表

| 表名 | 说明 |
|------|------|
| users | 用户表 |
| user_follows | 关注关系 |
| verification_codes | 验证码 |
| voice_test_results | 声音测试结果 |
| voice_test_songs | 推荐歌曲 |
| voice_cards | 声卡 |
| voice_card_templates | 声卡模板 |
| user_portraits | 用户画像 |
| analysis_records | 分析记录 |
| chat_rooms | 聊天室 |
| room_members | 房间成员 |
| mic_seats | 麦位 |
| room_messages | 房间消息 |
| mic_requests | 上麦申请 |
| conversations | 会话 |
| chat_messages | 私聊消息 |
| comment_notifications | 评论通知 |
| system_notifications | 系统通知 |
| square_posts | 广场动态 |
| post_comments | 评论 |
| post_likes | 动态点赞 |
| comment_likes | 评论点赞 |
| user_favorites | 收藏 |

## 许可证

MIT License
