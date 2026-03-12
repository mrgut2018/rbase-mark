# 敏感词检测代理使用指南

## 概述

`SensitiveWordDetectionAgent` 是基于阿里云文本审核增强版PLUS服务的敏感词检测代理，提供专业的文本内容安全检测功能。该代理支持多种检测场景，包括用户昵称检测、聊天内容检测、评论检测等。

## 功能特性

- ✅ **多种检测服务**: 支持昵称检测、聊天检测、评论检测、UGC审核等
- ✅ **智能风险评估**: 提供低、中、高三级风险等级判断
- ✅ **详细风险信息**: 返回风险原因、风险词汇、置信度等详细信息
- ✅ **批量检测**: 支持批量文本检测，提高处理效率
- ✅ **多地域支持**: 支持阿里云全球多个地域的服务接入
- ✅ **完善的错误处理**: 提供详细的错误信息和异常处理
- ✅ **环境变量配置**: 支持通过环境变量配置访问密钥

## 快速开始

### 1. 环境配置

首先需要配置阿里云的访问密钥环境变量：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID='your_access_key_id'
export ALIBABA_CLOUD_ACCESS_KEY_SECRET='your_access_key_secret'
```

### 2. 基础使用

```python
from deepsearcher.agent import SensitiveWordDetectionAgent, DetectionService

# 初始化检测代理
agent = SensitiveWordDetectionAgent(
    region="cn-shanghai",
    service_type=DetectionService.CHAT_DETECTION_PRO,
    timeout=30
)

# 检测文本内容
text = "这是一段需要检测的文本内容"
result = agent.detect_sensitive_words(text)

# 查看检测结果
print(f"有风险: {result.has_risk}")
print(f"风险等级: {result.risk_level}")
print(f"风险原因: {result.risk_reason}")

# 使用简化接口
is_safe, reason = agent.is_content_safe(text)
print(f"内容安全: {is_safe}, 原因: {reason}")
```

### 3. 批量检测

```python
# 批量检测多段文本
texts = [
    "第一段文本内容",
    "第二段文本内容", 
    "第三段文本内容"
]

results = agent.batch_detect(texts)

for i, result in enumerate(results):
    print(f"文本{i+1}: 风险={result.has_risk}, 原因={result.risk_reason}")
```

## API 参考

### SensitiveWordDetectionAgent

#### 构造函数

```python
SensitiveWordDetectionAgent(
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
    region: str = "cn-shanghai",
    service_type: DetectionService = DetectionService.CHAT_DETECTION_PRO,
    timeout: int = 30
)
```

**参数说明:**
- `access_key_id`: 阿里云访问密钥ID，可选，默认从环境变量获取
- `access_key_secret`: 阿里云访问密钥Secret，可选，默认从环境变量获取
- `region`: 阿里云地域，默认"cn-shanghai"
- `service_type`: 检测服务类型，默认聊天内容检测专业版
- `timeout`: 请求超时时间，默认30秒

#### 主要方法

##### detect_sensitive_words(content: str) -> DetectionResult

检测文本中的敏感词，返回详细的检测结果。

**参数:**
- `content`: 待检测的文本内容

**返回:** `DetectionResult` 对象，包含以下属性：
- `has_risk`: 是否有风险 (bool)
- `risk_level`: 风险等级 ("low"/"medium"/"high")
- `risk_reason`: 风险原因描述 (str)
- `labels`: 风险标签列表 (list)
- `confidence`: 置信度 (float)
- `risk_words`: 风险词汇 (str)
- `raw_response`: 原始API响应 (dict)

##### is_content_safe(content: str) -> Tuple[bool, str]

简化接口，检查内容是否安全。

**参数:**
- `content`: 待检测的文本内容

**返回:** 元组 (是否安全, 风险原因)

##### batch_detect(contents: list) -> list

批量检测敏感词。

**参数:**
- `contents`: 待检测的文本内容列表

**返回:** 检测结果列表

##### change_service_type(service_type: DetectionService)

更改检测服务类型。

**参数:**
- `service_type`: 新的检测服务类型

### DetectionService 枚举

支持的检测服务类型：

- `NICKNAME_DETECTION_PRO`: 用户昵称检测_专业版
- `CHAT_DETECTION_PRO`: 聊天内容检测_专业版  
- `COMMENT_DETECTION_PRO`: 评论检测_专业版
- `UGC_MODERATION_BYLLM`: UGC内容审核_基于大模型
- `AD_COMPLIANCE_DETECTION_PRO`: 广告合规检测_专业版

### RiskLevel 枚举

风险等级：

- `LOW`: 低风险
- `MEDIUM`: 中风险
- `HIGH`: 高风险

## 支持的地域

| 地域 | 代码 | 说明 |
|------|------|------|
| 华东2（上海） | cn-shanghai | 推荐使用 |
| 华北2（北京） | cn-beijing | |
| 华东1（杭州） | cn-hangzhou | |
| 华南1（深圳） | cn-shenzhen | |
| 西南1（成都） | cn-chengdu | |
| 新加坡 | ap-southeast-1 | |
| 英国（伦敦） | eu-west-1 | |
| 美国（弗吉尼亚） | us-east-1 | |
| 美国（硅谷） | us-west-1 | |
| 德国（法兰克福） | eu-central-1 | |

## 使用示例

### 不同服务类型检测

```python
from deepsearcher.agent import SensitiveWordDetectionAgent, DetectionService

# 昵称检测
nickname_agent = SensitiveWordDetectionAgent(
    service_type=DetectionService.NICKNAME_DETECTION_PRO
)
result = nickname_agent.detect_sensitive_words("用户昵称")

# 聊天内容检测
chat_agent = SensitiveWordDetectionAgent(
    service_type=DetectionService.CHAT_DETECTION_PRO
)
result = chat_agent.detect_sensitive_words("聊天消息内容")

# 评论检测
comment_agent = SensitiveWordDetectionAgent(
    service_type=DetectionService.COMMENT_DETECTION_PRO
)
result = comment_agent.detect_sensitive_words("用户评论内容")
```

### 服务类型切换

```python
agent = SensitiveWordDetectionAgent()

# 初始使用聊天检测
result1 = agent.detect_sensitive_words("测试内容")

# 切换到昵称检测
agent.change_service_type(DetectionService.NICKNAME_DETECTION_PRO)
result2 = agent.detect_sensitive_words("测试内容")
```

### 错误处理

```python
try:
    agent = SensitiveWordDetectionAgent()
    result = agent.detect_sensitive_words("测试内容")
    
    if result.has_risk:
        print(f"检测到风险: {result.risk_reason}")
        print(f"风险词汇: {result.risk_words}")
    else:
        print("内容安全")
        
except ValueError as e:
    print(f"配置错误: {e}")
except Exception as e:
    print(f"检测失败: {e}")
```

## 注意事项

1. **访问密钥安全**: 请妥善保管阿里云访问密钥，不要在代码中硬编码
2. **网络连接**: 确保网络可以访问阿里云服务端点
3. **配额限制**: 注意阿里云API的调用频率和配额限制
4. **地域选择**: 选择距离应用部署地区较近的地域以获得更好的响应速度
5. **服务开通**: 使用前需要在阿里云控制台开通文本审核增强版服务
6. **费用说明**: 该服务按调用量计费，请关注费用产生情况

## 故障排除

### 常见错误

1. **访问密钥未配置**
   ```
   ValueError: 阿里云访问密钥未配置
   ```
   解决方案: 设置环境变量 `ALIBABA_CLOUD_ACCESS_KEY_ID` 和 `ALIBABA_CLOUD_ACCESS_KEY_SECRET`

2. **网络连接失败**
   ```
   Exception: 网络请求失败
   ```
   解决方案: 检查网络连接和防火墙设置

3. **API调用失败**
   ```
   Exception: 敏感词检测API调用失败
   ```
   解决方案: 检查访问密钥权限和服务开通状态

4. **响应解析失败**
   ```
   Exception: 响应解析失败
   ```
   解决方案: 检查API响应格式，可能是服务端返回了非JSON格式的响应

### 调试建议

1. 启用详细日志记录
2. 检查网络连接状态
3. 验证访问密钥权限
4. 确认服务已正确开通
5. 查看阿里云控制台的API调用日志

## 相关链接

- [阿里云文本审核增强版文档](https://help.aliyun.com/document_detail/433945.html)
- [阿里云访问密钥管理](https://ram.console.aliyun.com/manage/ak)
- [阿里云内容安全控制台](https://yundun.console.aliyun.com/)

