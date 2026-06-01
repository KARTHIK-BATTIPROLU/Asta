# WebSocket Connection Issue - Troubleshooting Guide

## 🔴 Current Issue

**Frontend Error**: `WebSocket connection to 'ws://localhost:8000/ws/conversation' failed: HTTP 403`

**Status**: Server is running, but WebSocket connections are being rejected with 403 Forbidden.

---

## 🔍 Investigation Results

### What We Know
1. ✅ **Server is running** on port 8000
2. ✅ **Application startup complete**
3. ✅ **All services initialized** (MongoDB, Neo4j, Redis, Pinecone, Notion)
4. ✅ **WebSocket route registered** at `/ws/conversation`
5. ❌ **WebSocket connections rejected** with HTTP 403

### Authentication Status
- WebSocket authentication is **commented out** in `ws_routes.py`
- `verify_websocket_api_key` check is disabled
- Should allow connections without auth

---

## 🐛 Possible Causes

### 1. Middleware Blocking Connections
The HTTP middleware might be intercepting WebSocket upgrade requests.

### 2. CORS Configuration
Although CORS is set to `allow_origins=["*"]`, WebSocket upgrades might need special handling.

### 3. Firewall/Antivirus
Windows Firewall or antivirus might be blocking WebSocket connections.

### 4. Port Already in Use
Another process might be using port 8000.

---

## 🔧 Solutions to Try

### Solution 1: Check if Port is Available
```bash
netstat -ano | findstr :8000
```

If another process is using port 8000, kill it or use a different port.

### Solution 2: Disable WebSocket Auth Completely
The auth check is already commented out, but let's verify:

**File**: `backend/app/api/ws_routes.py` (line 110-115)
```python
@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    # TODO: Re-enable authentication after frontend is updated
    # if not verify_websocket_api_key(websocket):
    #     await websocket.close(code=4001)
    #     logger.warning("[WS] Unauthorized connection rejected")
    #     return

    await websocket.accept()  # This should accept immediately
```

### Solution 3: Add WebSocket to CORS Explicitly
**File**: `backend/app/main.py`

Update CORS middleware:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]  # Add this
)
```

### Solution 4: Test with Different Client
Try connecting from a different client to isolate the issue:

**Python Test**:
```bash
python test_websocket_simple.py
```

**Browser Console**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/conversation');
ws.onopen = () => console.log('Connected!');
ws.onerror = (e) => console.error('Error:', e);
```

### Solution 5: Check Windows Firewall
1. Open Windows Defender Firewall
2. Click "Allow an app through firewall"
3. Find Python and ensure both Private and Public are checked
4. Or temporarily disable firewall to test

### Solution 6: Use HTTP API Instead
While debugging WebSocket, use the HTTP API which is working:

**Endpoint**: `POST http://localhost:8000/api/chat`

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are my tasks today?", "session_id": "test-123"}'
```

---

## 📊 Server Status

| Component | Status |
|-----------|--------|
| Server | ✅ Running (port 8000) |
| HTTP API | ✅ Working |
| WebSocket | ❌ 403 Forbidden |
| Notion Integration | ✅ Ready |
| Workflows | ✅ Ready |

---

## 🎯 Recommended Next Steps

### Immediate (To Get Working)
1. **Use HTTP API** for testing Notion integration
2. **Check Windows Firewall** settings
3. **Verify no other process** is using port 8000

### Debug WebSocket
1. **Check server logs** when attempting connection
2. **Try different port** (e.g., 8001)
3. **Test from different machine** on same network

### Alternative
1. **Deploy to cloud** (Render, Railway, etc.) where WebSocket works reliably
2. **Use ngrok** to tunnel and test

---

## 💡 Workaround: Use HTTP API

While WebSocket is being debugged, you can use the HTTP API which is **fully functional**:

### Frontend Changes
Instead of WebSocket, use HTTP polling or Server-Sent Events (SSE):

```javascript
// Instead of WebSocket
async function sendMessage(message) {
  const response = await fetch('http://localhost:8000/api/chat', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: message,
      session_id: sessionId
    })
  });
  
  const data = await response.json();
  return data.reply;
}
```

---

## 📝 Summary

**Problem**: WebSocket connections rejected with 403  
**Impact**: Frontend can't connect to voice/realtime features  
**Workaround**: Use HTTP API (fully functional)  
**Status**: Investigating WebSocket auth/middleware issue  

**Notion Integration**: ✅ **WORKING** (tested via HTTP API)  
**Server**: ✅ **RUNNING**  
**Next**: Debug WebSocket or use HTTP API alternative

---

## 🔗 Related Files

- `backend/app/api/ws_routes.py` - WebSocket endpoint
- `backend/app/main.py` - Server configuration
- `backend/app/services/security.py` - Authentication
- `test_websocket.py` - WebSocket test script

---

**Last Updated**: April 24, 2026  
**Status**: Under Investigation  
**Priority**: Medium (HTTP API works as alternative)
