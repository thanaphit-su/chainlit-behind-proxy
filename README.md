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

เรามี `run.sh` script ที่ช่วยจัดการ proxy modes ให้ครับ

### ใช้ run.sh (แนะนำ)

```bash
chmod +x run.sh
./run.sh [MODE]
```

**Modes:**

| Mode | ใช้เมื่อ | คำสั่ง |
|------|---------|--------|
| `local` | รันบนเครื่องตัวเอง ไม่มี proxy | `./run.sh local` |
| `proxy-strip` | Proxy **ตัด path ออก** ก่อน forward (ทั่วไป) | `./run.sh proxy-strip` |
| `proxy-full` | Proxy **ส่ง path เต็ม** ไปยัง app | `./run.sh proxy-full` |
| `auto` | Auto-detect (default = proxy-strip) | `./run.sh` หรือ `./run.sh auto` |

### รูปแบบ Proxy ที่รองรับ

#### 1. Path-Stripping Proxy (แนะนำ - ใช้บ่อยที่สุด)

Proxy forward แบบนี้:
```
https://domain.com/{username}/proxy/{port}/  →  http://localhost:{port}/
```
**Proxy ตัด `/{username}/proxy/{port}/` ออก** ก่อนส่งไป app

```bash
./run.sh proxy-strip
# หรือ
chainlit run app.py -h --host 0.0.0.0 --port 8000
```

#### 2. Full-Path Proxy

Proxy forward แบบนี้:
```
https://domain.com/{username}/proxy/{port}/  →  http://localhost:{port}/{username}/proxy/{port}/
```
**Proxy ส่ง path เต็มไปยัง app**

```bash
./run.sh proxy-full
# หรือ
chainlit run app.py --root-path /{username}/proxy/{port} -h --host 0.0.0.0 --port 8000
```

### แบบปกติ (Local Development)

```bash
./run.sh local
# หรือ
source .venv/bin/activate
chainlit run app.py -w
```

### รันหลัง Proxy (Production)

สำหรับ auto-tunnel ที่ forward จาก `https://domain.com/{username}/proxy/8000/` → `http://localhost:8000/` (ตัด path ออก):

```bash
./run.sh proxy-strip
```

**อธิบาย flags:**
- `--root-path` - กำหนด root path (ใช้เฉพาะกับ full-path proxy)
- `-h` (หรือ `--headless`) - ไม่เปิด browser อัตโนมัติ (สำหรับ production)
- `--host 0.0.0.0` - รับ connection จากทุก IP (สำหรับ Docker/remote access)
- `--port 8000` - กำหนด port

## หมายเหตุเกี่ยวกับ Proxy

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
