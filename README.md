# Chainlit + LangGraph Agentic Chat Application

โปรเจกต์นี้เป็น **Simple Agent Chat Application** ที่ integrate ระหว่าง **Chainlit** (สำหรับ UI) และ **LangGraph** (สำหรับ Agentic Loop) พร้อมรองรับ **OpenAI Compatible API**

**รองรับ Proxy Pattern:** `/{username}/proxy/{portNumber}` — ใช้ได้กับทุก user โดยอัตโนมัติ

## โครงสร้างโปรเจกต์

```
.
├── .env                  # Environment variables (ต้องกรอกค่าก่อนใช้งาน)
├── .env.example          # Environment variables template
├── .venv/                # Virtual environment (สร้างโดย uv)
├── src/
│   ├── app.py            # Chainlit Application (Entry point)
│   ├── agent.py          # LangGraph Agentic Loop implementation
│   ├── tools.py          # เครื่องมือที่ Agent สามารถเรียกใช้ได้
│   └── proxy_middleware.py  # ASGI middleware สำหรับ proxy
├── server/
│   ├── asgi_app.py       # Custom ASGI app สำหรับรันหลัง proxy
│   └── run_server.py     # Standalone server runner
├── scripts/
│   └── run.sh            # Script รัน app พร้อมรองรับ proxy modes
├── pyproject.toml        # Project configuration & dependencies
├── README.md             # เอกสารนี้
└── TECHNICAL_SPEC.md     # Technical specification
```

## องค์ประกอบของ Agentic Loop

1. **Trigger**: เหตุการณ์เริ่มต้นเมื่อผู้ใช้ส่งข้อความ
2. **Reason (การคิด)**: LLM ประมวลผลและวางแผนว่าจะต้องทำอะไรต่อไป
3. **Act (การกระทำ)**: สั่งใช้เครื่องมือ (Tools) เช่น ค้นหาข้อมูล, คำนวณ, เช็คเวลา
4. **Observe (การสังเกต)**: อ่านและประเมินผลลัพธ์ที่ได้กลับมาจากเครื่องมือ
5. **Stop Rules (เงื่อนไขหยุด)**: หยุดวนลูปเมื่อบรรลุเป้าหมาย, เกิดข้อผิดพลาด, หรือครบจำนวนรอบสูงสุด

## Tools ที่มีให้ใช้งาน

- `search_web` - ค้นหาข้อมูลบนเว็บ (simulated)
- `calculate` - คำนวณสมการคณิตศาสตร์
- `get_current_time` - ดึงเวลาปัจจุบัน
- `random_number` - สุ่มตัวเลข
- `weather_info` - ดูข้อมูลสภาพอากาศ (simulated)

## การติดตั้ง

### 1. ติดตั้ง Dependencies ด้วย uv

```bash
uv venv
uv pip install -e .
```

### 2. ตั้งค่า Environment Variables

แก้ไขไฟล์ `.env` และกรอกค่าตามตัวอย่าง:

```env
# OpenAI Compatible API Configuration
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-3.5-turbo

# Application Configuration
CHAINLIT_PORT=8000

# Proxy Configuration (optional - auto-detected from username)
# Pattern: /{username}/proxy/{portNumber}
# Example: CHAINLIT_PROXY_PATH=/thanaphits/proxy/8000
```

> **Note**: รองรับทุก OpenAI Compatible API เช่น Ollama, vLLM, LM Studio, Together AI, ฯลฯ
> **Proxy Path**: ระบบจะ auto-detect username จาก `$USER` โดยอัตโนมัติ

## การรัน Application

> **⚠️ สำคัญ:** ต้องรันจาก **project root** (โฟลเดอร์ที่มี `.env` อยู่) เสมอ

```bash
cd /path/to/chainlit  # ต้อง cd มาที่นี่ก่อน
```

### วิธีที่ 1: ใช้ `run.sh` (แนะนำ)

```bash
# รันหลัง proxy (default)
./scripts/run.sh proxy-strip

# รัน local (ไม่มี proxy)
./scripts/run.sh local

# ดู help
./scripts/run.sh help
```

**Output ที่ควรเห็น:**
```bash
==========================================
Chainlit + LangGraph Agent Runner
==========================================

Mode: Proxy with Path Stripping + Middleware
URL: http://0.0.0.0:8000/
Proxy Path: /thanaphits/proxy/8000/
(From .env file)

✅ Set CHAINLIT_ROOT_PATH=/thanaphits/proxy/8000
🚀 Starting Chainlit app on http://0.0.0.0:8000/
```

### วิธีที่ 2: รันตรงๆ ด้วย Python

```bash
# ต้องอยู่ที่ project root
python server/run_server.py
```

### วิธีที่ 3: ใช้ `chainlit run` (ไม่ผ่าน proxy middleware)

```bash
# Local development
chainlit run src/app.py -w

# หรือรันหลัง proxy
chainlit run src/app.py --root-path /thanaphits/proxy/8000 -h --host 0.0.0.0
```

### ⚠️ ห้ามรันจาก sub-directory

```bash
# ❌ ผิด - จะหา .env ไม่เจอ
cd server
python run_server.py

# ✅ ถูก - รันจาก project root
cd ..
python server/run_server.py
```

## แก้ไขปัญหา

### Model '' was not found

ถ้าได้ error นี้ แสดงว่า `.env` ไม่ถูกโหลด (ค่า model เป็น empty string):

```json
{"detail": "Model '' was not found"}
```

**สาเหตุ:** รันจากผิด directory (ไม่ใช่ project root)

**แก้ไข:**
```bash
# ❌ ผิด
cd server && python run_server.py

# ✅ ถูก
cd /path/to/project
python server/run_server.py
```

### ตรวจสอบว่า .env โหลดถูกต้อง

```bash
source .venv/bin/activate
python -c "
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('.').resolve() / '.env')
import os
print('BASE_URL:', os.getenv('OPENAI_API_BASE_URL'))
print('MODEL:', os.getenv('OPENAI_MODEL'))
"
```

ถ้าแสดงค่าถูกต้อง = `.env` โหลดสำเร็จ

- Chainlit ใช้ **WebSockets** ดังนั้น proxy ต้องรองรับ WebSocket proxying
- หากมีปัญหาเรื่อง sticky sessions ให้ตั้งค่า `transports = ["websocket"]` ใน `.chainlit/config.toml`
- หากมีปัญหา CORS ให้แก้ไข `allow_origins` ใน `.chainlit/config.toml`

## การตั้งค่าเพิ่มเติม

หากต้องการปรับแต่ง Chainlit configuration (เช่น CORS, theme, ฯลฯ):

```bash
chainlit init
```

คำสั่งนี้จะสร้างไฟล์ `.chainlit/config.toml` ที่สามารถแก้ไขได้ตามต้องการ

## Dependencies หลัก

- **chainlit** - Python framework สำหรับสร้าง conversational AI UI
- **langgraph** - Library สำหรับสร้าง stateful, multi-actor applications ด้วย LLMs
- **langchain-openai** - Integration กับ OpenAI Compatible API
- **python-dotenv** - โหลด environment variables จากไฟล์ `.env`
