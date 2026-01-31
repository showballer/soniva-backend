# Soniva Backend API 文档

> 版本: 1.0.0
> 基础路径: `/api/v1`
> 认证方式: Bearer Token (JWT)

---

## 目录

1. [通用说明](#通用说明)
2. [认证模块](#1-认证模块-auth)
3. [声音测试模块](#2-声音测试模块-voice-test)
4. [声卡模块](#3-声卡模块-voice-card)
5. [识Ta模块](#4-识ta模块-identify)
6. [聊天室模块](#5-聊天室模块-chat-room)
7. [消息中心模块](#6-消息中心模块-message)
8. [广场模块](#7-广场模块-square)
9. [用户模块](#8-用户模块-user)

---

## 通用说明

### 请求头

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### 统一响应格式

**成功响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**分页响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [ ... ],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

**错误响应:**
```json
{
  "code": 400,
  "message": "错误信息",
  "data": null
}
```

### 错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未授权/Token无效 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 500 | 服务器内部错误 |

---

## 1. 认证模块 (Auth)

### 1.1 发送验证码

```
POST /api/v1/auth/send-code
```

**请求体:**
```json
{
  "phone": "13800138000",
  "type": "register"  // register/login/reset_password
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Verification code sent",
    "expires_in": 300
  }
}
```

> ⚠️ **TODO**: 接入阿里云短信服务

---

### 1.2 用户注册

```
POST /api/v1/auth/register
```

**请求体:**
```json
{
  "phone": "13800138000",
  "verification_code": "123456",
  "password": "password123",
  "name": "用户昵称",
  "is_anonymous": true
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid",
    "name": "用户昵称",
    "avatar": null,
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 7200
  }
}
```

---

### 1.3 用户登录

```
POST /api/v1/auth/login
```

**请求体:**
```json
{
  "phone": "13800138000",
  "password": "password123"
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid",
    "name": "用户昵称",
    "avatar": "/uploads/avatars/xxx.jpg",
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 7200
  }
}
```

---

### 1.4 刷新Token

```
POST /api/v1/auth/refresh
```

**请求体:**
```json
{
  "refresh_token": "eyJ..."
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 7200
  }
}
```

---

### 1.5 退出登录

```
POST /api/v1/auth/logout
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Logged out successfully"
  }
}
```

---

## 2. 声音测试模块 (Voice Test)

### 2.1 上传音频文件

```
POST /api/v1/voice-test/upload
```

**请求:** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 音频文件 (mp3/wav/m4a/aac/flac/ogg, 最大30MB) |
| text_content | string | 是 | 朗读的文本内容 |

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "file_id": "uuid",
    "file_url": "/uploads/voice/uuid.mp3",
    "duration": 15.32
  }
}
```

---

### 2.2 声音分析 🤖

```
POST /api/v1/voice-test/analyze
```

**请求体:**
```json
{
  "file_id": "uuid",
  "text_content": "朗读的文本内容",
  "gender": "female"  // female/male
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "result_id": "uuid",
    "voice_type_scores": {
      "萝莉音": 15.2,
      "少女音": 45.8,
      "御姐音": 20.5,
      "女王音": 5.3,
      "软萌音": 8.2,
      "温柔音": 3.0,
      "中性音": 1.5,
      "甜美音": 0.5,
      "知性音": 0.0,
      "烟嗓音": 0.0
    },
    "main_voice_type": "少女音",
    "tags": ["清澈", "明亮", "稳定"],
    "overall_score": 8.5,
    "charm_index": 7.8,
    "hearing_age": 22,
    "hearing_height": 165,
    "voice_attribute": "可攻可受",
    "color_temperature": "中性",
    "emotional_summary": "Young female voice - F0 in young female range",
    "advanced_suggestion": "Clear enunciation, Pure and high",
    "recommended_songs": [
      {
        "name": "小幸运",
        "artist": "田馥甄",
        "reason": "音域契合，适合展现声音特质"
      }
    ],
    "created_at": "2024-01-01T12:00:00"
  }
}
```

> 🤖 **AI功能说明:**
>
> **当前实现 (基于librosa):**
> - 基频F0提取 (音高分析)
> - MFCC特征提取
> - 频谱分析 (质心、对比度、平坦度)
> - 谐波比计算 (清晰度)
> - 过零率分析 (气息感)
> - RMS能量分析
> - 共振峰估计
> - 基于规则的声音类型打分
>
> **TODO - 待接入AI服务 (FastGPT):**
> - [ ] 更精准的声音类型识别模型
> - [ ] 智能歌曲推荐算法
> - [ ] 个性化进阶建议生成
> - [ ] 情感分析与总结生成

---

### 2.3 获取测试历史

```
GET /api/v1/voice-test/history?page=1&page_size=10
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "result_id": "uuid",
        "main_voice_type": "少女音",
        "overall_score": 8.5,
        "tags": ["清澈", "明亮"],
        "created_at": "2024-01-01T12:00:00",
        "audio_url": "/uploads/voice/xxx.mp3"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 10,
    "total_pages": 1
  }
}
```

---

### 2.4 获取测试结果详情

```
GET /api/v1/voice-test/result/{result_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "result_id": "uuid",
    "voice_type_scores": { ... },
    "main_voice_type": "少女音",
    "tags": ["清澈", "明亮"],
    "overall_score": 8.5,
    "charm_index": 7.8,
    "hearing_age": 22,
    "hearing_height": 165,
    "voice_attribute": "可攻可受",
    "color_temperature": "中性",
    "emotional_summary": "...",
    "advanced_suggestion": "...",
    "recommended_songs": [ ... ],
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 2.5 删除测试结果

```
DELETE /api/v1/voice-test/result/{result_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Deleted successfully"
  }
}
```

---

## 3. 声卡模块 (Voice Card)

### 3.1 获取模板列表

```
GET /api/v1/voice-card/templates
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "templates": [
      {
        "id": "neon_party",
        "name": "霓虹派对",
        "preview_url": "/templates/neon_party.png",
        "colors": ["#FE2C55", "#7C3AED"],
        "style": "gradient"
      },
      {
        "id": "starry_dream",
        "name": "星空梦境",
        "preview_url": "/templates/starry_dream.png",
        "colors": ["#2DE2E6", "#0B0B0F"],
        "style": "stars"
      },
      {
        "id": "aurora",
        "name": "极光幻影",
        "preview_url": "/templates/aurora.png",
        "colors": ["#2DE2E6", "#00B894"],
        "style": "aurora"
      },
      {
        "id": "deep_sea",
        "name": "深海蔚蓝",
        "preview_url": "/templates/deep_sea.png",
        "colors": ["#1E3A5F", "#2DE2E6"],
        "style": "bubbles"
      },
      {
        "id": "minimal",
        "name": "简约纯色",
        "preview_url": "/templates/minimal.png",
        "colors": ["#0B0B0F", "#FFFFFF"],
        "style": "minimal"
      }
    ]
  }
}
```

---

### 3.2 生成声卡

```
POST /api/v1/voice-card/generate
```

**请求体:**
```json
{
  "result_id": "uuid",
  "template_id": "neon_party"
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "card_id": "uuid",
    "template_id": "neon_party",
    "image_url": "/uploads/voice_cards/uuid.png",
    "voice_type": "少女音",
    "overall_score": 8.5,
    "tags": ["清澈", "明亮"],
    "created_at": "2024-01-01T12:00:00"
  }
}
```

> ⚠️ **TODO**: 实现声卡图片渲染生成功能

---

### 3.3 获取我的声卡列表

```
GET /api/v1/voice-card/my-cards?page=1&page_size=10
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "card_id": "uuid",
        "template_id": "neon_party",
        "image_url": "/uploads/voice_cards/uuid.png",
        "voice_type": "少女音",
        "overall_score": 8.5,
        "tags": ["清澈", "明亮"],
        "share_count": 10,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 3,
    "page": 1,
    "page_size": 10,
    "total_pages": 1
  }
}
```

---

### 3.4 获取声卡详情

```
GET /api/v1/voice-card/{card_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "card_id": "uuid",
    "template_id": "neon_party",
    "image_url": "/uploads/voice_cards/uuid.png",
    "voice_type": "少女音",
    "overall_score": 8.5,
    "tags": ["清澈", "明亮"],
    "share_count": 10,
    "is_public": true,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 3.5 分享声卡

```
POST /api/v1/voice-card/{card_id}/share
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "share_count": 11,
    "share_url": "http://localhost:8000/card/uuid"
  }
}
```

---

### 3.6 删除声卡

```
DELETE /api/v1/voice-card/{card_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Deleted successfully"
  }
}
```

---

## 4. 识Ta模块 (Identify)

### 4.1 上传目标声音

```
POST /api/v1/identify/upload
```

**请求:** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 音频文件 (mp3/wav/m4a/aac/flac/ogg, 最大30MB) |

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "file_id": "uuid",
    "file_url": "/uploads/voice/uuid.mp3",
    "duration": 15.32
  }
}
```

---

### 4.2 分析生成画像 🤖

```
POST /api/v1/identify/analyze
```

**请求体:**
```json
{
  "file_id": "uuid",
  "target_nickname": "小明",
  "relationship": "friend"  // friend/partner/colleague/stranger
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "portrait_id": "uuid",
    "nickname": "小明",
    "mbti": "ENFP",
    "personality_tags": ["活泼", "开朗", "真诚"],
    "personality_description": "热情洋溢，富有创造力，喜欢探索新可能",
    "compatibility_score": 85.5,
    "relationship": "friend",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

> 🤖 **AI功能说明:**
>
> **当前实现 (基于规则):**
> - 基于声音特征的MBTI预测
> - 基于音高稳定性、谐波比等的性格标签生成
> - 简单的兼容性评分算法
>
> **TODO - 待接入AI服务 (FastGPT):**
> - [ ] 深度学习声纹性格分析模型
> - [ ] AI生成个性化性格描述
> - [ ] 多维度兼容性分析
> - [ ] 社交互动建议生成
> - [ ] 结合头像的综合分析

---

### 4.3 获取画像列表

```
GET /api/v1/identify/portraits?page=1&page_size=10
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "portrait_id": "uuid",
        "nickname": "小明",
        "avatar": null,
        "mbti": "ENFP",
        "personality_tags": ["活泼", "开朗"],
        "compatibility_score": 85.5,
        "relationship": "friend",
        "is_favorite": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 10,
    "total_pages": 1
  }
}
```

---

### 4.4 获取画像详情

```
GET /api/v1/identify/portrait/{portrait_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "portrait_id": "uuid",
    "nickname": "小明",
    "avatar": null,
    "mbti": "ENFP",
    "personality_tags": ["活泼", "开朗", "真诚"],
    "personality_description": "热情洋溢，富有创造力，喜欢探索新可能",
    "compatibility_score": 85.5,
    "relationship": "friend",
    "audio_url": "/uploads/voice/xxx.mp3",
    "is_favorite": false,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 4.5 收藏/取消收藏画像

```
POST /api/v1/identify/portrait/{portrait_id}/favorite
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_favorite": true
  }
}
```

---

### 4.6 删除画像

```
DELETE /api/v1/identify/portrait/{portrait_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Deleted successfully"
  }
}
```

---

## 5. 聊天室模块 (Chat Room)

### 5.1 创建房间

```
POST /api/v1/chat-room/create
```

**请求体:**
```json
{
  "name": "我的小窝",
  "room_type": "eight_mic",  // eight_mic/one_on_one
  "is_private": false,
  "password": null
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "room_id": "uuid",
    "room_code": "A1B2C3D4",
    "name": "我的小窝",
    "room_type": "eight_mic",
    "is_private": false,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 5.2 获取房间列表

```
GET /api/v1/chat-room/list?page=1&page_size=20&room_type=eight_mic
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "room_id": "uuid",
        "room_code": "A1B2C3D4",
        "name": "我的小窝",
        "room_type": "eight_mic",
        "cover_url": null,
        "current_members": 5,
        "max_members": 100,
        "host": {
          "user_id": "uuid",
          "name": "房主昵称",
          "avatar": "/uploads/avatars/xxx.jpg"
        }
      }
    ],
    "total": 10,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 5.3 获取房间详情

```
GET /api/v1/chat-room/{room_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "room_id": "uuid",
    "room_code": "A1B2C3D4",
    "name": "我的小窝",
    "notice": "欢迎来到我的小窝",
    "room_type": "eight_mic",
    "cover_url": null,
    "background_url": null,
    "current_members": 5,
    "max_members": 100,
    "is_private": false,
    "host": {
      "user_id": "uuid",
      "name": "房主昵称",
      "avatar": "/uploads/avatars/xxx.jpg"
    },
    "mic_seats": [
      {
        "seat_index": 0,
        "user": {
          "user_id": "uuid",
          "name": "房主",
          "avatar": "/uploads/avatars/xxx.jpg"
        },
        "is_muted": false,
        "is_locked": false
      },
      {
        "seat_index": 1,
        "user": null,
        "is_muted": false,
        "is_locked": false
      }
    ],
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 5.4 加入房间

```
POST /api/v1/chat-room/{room_id}/join?password=xxx
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "room_id": "uuid",
    "message": "Joined successfully"
  }
}
```

---

### 5.5 离开房间

```
POST /api/v1/chat-room/{room_id}/leave
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Left room"
  }
}
```

---

### 5.6 申请上麦

```
POST /api/v1/chat-room/{room_id}/mic/request?seat_index=1
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "request_id": "uuid",
    "message": "Mic request sent"
  }
}
```

---

### 5.7 批准上麦申请 (房主)

```
POST /api/v1/chat-room/{room_id}/mic/approve/{request_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Request approved"
  }
}
```

---

### 5.8 下麦

```
POST /api/v1/chat-room/{room_id}/mic/leave
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Left mic"
  }
}
```

---

### 5.9 静音/取消静音

```
POST /api/v1/chat-room/{room_id}/mic/mute/{seat_index}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "seat_index": 1,
    "is_muted": true
  }
}
```

---

### 5.10 关闭房间 (房主)

```
POST /api/v1/chat-room/{room_id}/close
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Room closed"
  }
}
```

---

### 5.11 获取房间消息历史

```
GET /api/v1/chat-room/{room_id}/messages?page=1&page_size=50
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "message_id": "uuid",
        "user": {
          "user_id": "uuid",
          "name": "用户昵称",
          "avatar": "/uploads/avatars/xxx.jpg"
        },
        "content": "大家好",
        "message_type": "text",
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 50,
    "total_pages": 2
  }
}
```

---

### 5.12 WebSocket 实时通讯

```
WS /api/v1/chat-room/ws/{room_id}?token=<access_token>
```

**发送消息:**
```json
{
  "type": "message",
  "content": "大家好"
}
```

**接收消息类型:**

用户加入:
```json
{
  "type": "user_joined",
  "user": {
    "user_id": "uuid",
    "name": "用户昵称",
    "avatar": "/uploads/avatars/xxx.jpg"
  },
  "timestamp": "2024-01-01T12:00:00"
}
```

聊天消息:
```json
{
  "type": "message",
  "message_id": "uuid",
  "user": {
    "user_id": "uuid",
    "name": "用户昵称",
    "avatar": "/uploads/avatars/xxx.jpg"
  },
  "content": "大家好",
  "timestamp": "2024-01-01T12:00:00"
}
```

用户离开:
```json
{
  "type": "user_left",
  "user_id": "uuid",
  "timestamp": "2024-01-01T12:00:00"
}
```

> ⚠️ **TODO - 待实现:**
> - [ ] 语音实时传输 (WebRTC)
> - [ ] 礼物系统
> - [ ] 房间互动特效
> - [ ] 语音消息AI分析 🤖

---

## 6. 消息中心模块 (Message)

### 6.1 获取会话列表

```
GET /api/v1/message/conversations?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "conversation_id": "uuid",
        "user": {
          "user_id": "uuid",
          "name": "用户昵称",
          "avatar": "/uploads/avatars/xxx.jpg"
        },
        "last_message": "你好",
        "last_message_type": "text",
        "unread_count": 3,
        "updated_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 10,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 6.2 获取/创建会话

```
GET /api/v1/message/conversation/{user_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "conversation_id": "uuid",
    "user": {
      "user_id": "uuid",
      "name": "用户昵称",
      "avatar": "/uploads/avatars/xxx.jpg"
    }
  }
}
```

---

### 6.3 获取聊天记录

```
GET /api/v1/message/messages/{conversation_id}?page=1&page_size=50
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "message_id": "uuid",
        "sender_id": "uuid",
        "receiver_id": "uuid",
        "content": "你好",
        "message_type": "text",
        "is_read": true,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 50,
    "total_pages": 2
  }
}
```

---

### 6.4 发送私信

```
POST /api/v1/message/send
```

**请求体:**
```json
{
  "receiver_id": "uuid",
  "content": "你好",
  "message_type": "text"  // text/image/voice
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message_id": "uuid",
    "conversation_id": "uuid",
    "content": "你好",
    "message_type": "text",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 6.5 获取评论通知

```
GET /api/v1/message/comments?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "notification_id": "uuid",
        "from_user": {
          "user_id": "uuid",
          "name": "用户昵称",
          "avatar": "/uploads/avatars/xxx.jpg"
        },
        "post_id": "uuid",
        "comment_id": "uuid",
        "content": "评论了你的动态: 写得真好",
        "notification_type": "comment",
        "is_read": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 6.6 标记评论通知已读

```
POST /api/v1/message/comments/read
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "All marked as read"
  }
}
```

---

### 6.7 获取系统通知

```
GET /api/v1/message/notifications?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "notification_id": "uuid",
        "title": "系统升级通知",
        "content": "系统将于今晚0点进行维护升级",
        "notification_type": "system",
        "action_url": null,
        "is_read": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 3,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 6.8 标记系统通知已读

```
POST /api/v1/message/notifications/read
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "All marked as read"
  }
}
```

---

### 6.9 获取未读消息数量

```
GET /api/v1/message/unread-counts
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "private_messages": 5,
    "comments": 3,
    "notifications": 2,
    "total": 10
  }
}
```

---

## 7. 广场模块 (Square)

### 7.1 获取动态列表

```
GET /api/v1/square/feed?page=1&page_size=20&feed_type=recommend
```

**参数:**
- `feed_type`: recommend(推荐) / following(关注) / latest(最新)

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "post_id": "uuid",
        "author": {
          "user_id": "uuid",
          "name": "用户昵称",
          "avatar": "/uploads/avatars/xxx.jpg",
          "is_anonymous": false
        },
        "content": "今天心情很好~",
        "voice_url": "/uploads/voice/xxx.mp3",
        "images": ["/uploads/posts/xxx.jpg"],
        "tags": ["日常", "心情"],
        "like_count": 100,
        "comment_count": 20,
        "share_count": 5,
        "is_liked": false,
        "is_favorited": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 50,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  }
}
```

> ⚠️ **TODO - 待优化:**
> - [ ] AI推荐算法优化 🤖
> - [ ] 基于用户声音特征的内容推荐

---

### 7.2 发布动态

```
POST /api/v1/square/post
```

**请求体:**
```json
{
  "content": "今天心情很好~",
  "voice_url": "/uploads/voice/xxx.mp3",
  "images": ["/uploads/posts/xxx.jpg"],
  "tags": ["日常", "心情"]
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "post_id": "uuid",
    "content": "今天心情很好~",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 7.3 获取动态详情

```
GET /api/v1/square/post/{post_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "post_id": "uuid",
    "author": {
      "user_id": "uuid",
      "name": "用户昵称",
      "avatar": "/uploads/avatars/xxx.jpg",
      "is_anonymous": false
    },
    "content": "今天心情很好~",
    "voice_url": "/uploads/voice/xxx.mp3",
    "images": ["/uploads/posts/xxx.jpg"],
    "tags": ["日常", "心情"],
    "like_count": 100,
    "comment_count": 20,
    "share_count": 5,
    "is_liked": false,
    "is_favorited": false,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 7.4 删除动态

```
DELETE /api/v1/square/post/{post_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Deleted successfully"
  }
}
```

---

### 7.5 点赞/取消点赞

```
POST /api/v1/square/post/{post_id}/like
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_liked": true,
    "like_count": 101
  }
}
```

---

### 7.6 获取评论列表

```
GET /api/v1/square/post/{post_id}/comments?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "comment_id": "uuid",
        "author": {
          "user_id": "uuid",
          "name": "用户昵称",
          "avatar": "/uploads/avatars/xxx.jpg"
        },
        "content": "写得真好",
        "like_count": 10,
        "reply_count": 2,
        "replies": [
          {
            "comment_id": "uuid",
            "author": {
              "user_id": "uuid",
              "name": "用户昵称",
              "avatar": "/uploads/avatars/xxx.jpg"
            },
            "content": "谢谢",
            "like_count": 1,
            "created_at": "2024-01-01T12:01:00"
          }
        ],
        "is_liked": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 20,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 7.7 发表评论

```
POST /api/v1/square/post/{post_id}/comment
```

**请求体:**
```json
{
  "content": "写得真好",
  "parent_id": null  // 回复评论时传入父评论ID
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "comment_id": "uuid",
    "content": "写得真好",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 7.8 评论点赞/取消点赞

```
POST /api/v1/square/comment/{comment_id}/like
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_liked": true,
    "like_count": 11
  }
}
```

---

### 7.9 删除评论

```
DELETE /api/v1/square/comment/{comment_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Deleted successfully"
  }
}
```

---

### 7.10 收藏/取消收藏动态

```
POST /api/v1/square/post/{post_id}/favorite
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_favorited": true
  }
}
```

---

## 8. 用户模块 (User)

### 8.1 获取我的资料

```
GET /api/v1/user/profile
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid",
    "phone": "138****0000",
    "name": "用户昵称",
    "avatar": "/uploads/avatars/xxx.jpg",
    "bio": "个人简介",
    "gender": "female",
    "birthday": "2000-01-01",
    "location": "北京",
    "is_anonymous": false,
    "voice_type": "少女音",
    "statistics": {
      "test_count": 5,
      "post_count": 10,
      "follower_count": 100,
      "following_count": 50
    },
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

### 8.2 更新资料

```
PUT /api/v1/user/profile
```

**请求体:**
```json
{
  "name": "新昵称",
  "bio": "新简介",
  "gender": "female",
  "birthday": "2000-01-01",
  "location": "北京"
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Profile updated",
    "name": "新昵称",
    "bio": "新简介",
    "gender": "female",
    "birthday": "2000-01-01",
    "location": "北京"
  }
}
```

---

### 8.3 上传头像

```
POST /api/v1/user/avatar
```

**请求:** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 图片文件 (jpg/jpeg/png/gif/webp, 最大5MB) |

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "avatar": "/uploads/avatars/uuid.jpg"
  }
}
```

---

### 8.4 修改密码

```
PUT /api/v1/user/password
```

**请求体:**
```json
{
  "old_password": "oldpass123",
  "new_password": "newpass123"
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "message": "Password updated successfully"
  }
}
```

---

### 8.5 更新匿名设置

```
PUT /api/v1/user/anonymous
```

**请求体:**
```json
{
  "is_anonymous": true
}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_anonymous": true
  }
}
```

---

### 8.6 获取用户资料

```
GET /api/v1/user/{user_id}
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid",
    "name": "用户昵称",
    "avatar": "/uploads/avatars/xxx.jpg",
    "bio": "个人简介",
    "is_anonymous": false,
    "voice_type": "少女音",
    "statistics": {
      "post_count": 10,
      "follower_count": 100,
      "following_count": 50
    },
    "is_following": false
  }
}
```

---

### 8.7 关注/取消关注

```
POST /api/v1/user/{user_id}/follow
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_following": true
  }
}
```

---

### 8.8 获取粉丝列表

```
GET /api/v1/user/{user_id}/followers?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "user_id": "uuid",
        "name": "粉丝昵称",
        "avatar": "/uploads/avatars/xxx.jpg",
        "bio": "个人简介",
        "is_following": false
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

---

### 8.9 获取关注列表

```
GET /api/v1/user/{user_id}/following?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "user_id": "uuid",
        "name": "关注的人",
        "avatar": "/uploads/avatars/xxx.jpg",
        "bio": "个人简介",
        "is_following": true
      }
    ],
    "total": 50,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  }
}
```

---

### 8.10 获取我的收藏

```
GET /api/v1/user/me/favorites?page=1&page_size=20&target_type=post
```

**参数:**
- `target_type`: post / user (可选)

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "favorite_id": "uuid",
        "target_type": "post",
        "target_id": "uuid",
        "target": {
          "post_id": "uuid",
          "content": "动态内容预览...",
          "author": {
            "user_id": "uuid",
            "name": "作者昵称",
            "avatar": "/uploads/avatars/xxx.jpg"
          }
        },
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 10,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

### 8.11 获取用户动态

```
GET /api/v1/user/{user_id}/posts?page=1&page_size=20
```

**响应:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "post_id": "uuid",
        "content": "今天心情很好~",
        "voice_url": "/uploads/voice/xxx.mp3",
        "images": ["/uploads/posts/xxx.jpg"],
        "tags": ["日常", "心情"],
        "like_count": 100,
        "comment_count": 20,
        "is_liked": false,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "total": 10,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

## AI功能待实现清单

| 模块 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 声音测试 | 声音类型识别模型 | 替换当前基于规则的算法，使用深度学习模型 | 高 |
| 声音测试 | 智能歌曲推荐 | 基于声音特征推荐适合的歌曲 | 中 |
| 声音测试 | 个性化进阶建议 | AI生成针对性的声音训练建议 | 中 |
| 声音测试 | 情感分析 | 分析声音中的情感特征 | 低 |
| 识Ta | 声纹性格分析 | 深度学习模型分析性格 | 高 |
| 识Ta | AI性格描述生成 | 基于分析结果生成个性化描述 | 中 |
| 识Ta | 多维度兼容性分析 | 综合多项指标计算兼容性 | 中 |
| 识Ta | 头像综合分析 | 结合头像进行多模态分析 | 低 |
| 聊天室 | 语音消息AI分析 | 实时分析语音消息的情感和特征 | 低 |
| 广场 | AI内容推荐 | 基于用户特征的个性化推荐 | 中 |

---

## 更新日志

### v1.0.0 (2024-01-31)
- 初始版本发布
- 完成所有基础API端点
- 实现基于librosa的声音特征提取
- 实现基于规则的声音类型分类算法
