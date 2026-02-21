import httpx
import asyncio

async def run():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Login
        r_login = await client.post('http://localhost:8000/auth/login', json={'tenant_name': 'acme-corp', 'email': 'recruiter@acme.com', 'password': 'password123'})
        token = r_login.json().get('access_token')
        print(f"Login Status: {r_login.status_code}")
        
        # Chat
        headers = {"Authorization": f"Bearer {token}"}
        r_chat = await client.post('http://localhost:8000/chat', json={'content': 'hello what you can do'}, headers=headers)
        print(f"Chat Status: {r_chat.status_code}")
        print(f"Chat Response: {r_chat.text}")

if __name__ == "__main__":
    if __import__("sys").platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
