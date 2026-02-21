import httpx
import asyncio

async def run():
    async with httpx.AsyncClient() as client:
        r = await client.post('http://localhost:8000/auth/login', json={'tenant_name': 'acme-corp', 'email': 'recruiter@acme.com', 'password': 'password123'})
        print("Status", r.status_code)
        print("Response", r.text)

if __name__ == "__main__":
    if __import__("sys").platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
