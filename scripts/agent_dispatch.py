import os
import asyncio
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_pending_links():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set in environment.")
        return []
        
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        async with conn.cursor() as cur:
            # Query for pending links, joining with core.roster to get candidate details
            query = """
                SELECT 
                    pl.id, 
                    pl.source_name, 
                    pl.source_team, 
                    pl.match_score, 
                    pl.match_method,
                    pl.source_context->>'title' as context_title,
                    r.first_name, 
                    r.last_name, 
                    r.position, 
                    r.team
                FROM scouting.pending_links pl
                LEFT JOIN core.roster r ON r.id = pl.candidate_roster_id::integer
                WHERE pl.status = 'pending'
                ORDER BY pl.created_at ASC
                LIMIT 5
            """
            await cur.execute(query)
            return await cur.fetchall()

async def main():
    links = await get_pending_links()
    if not links:
        print("No pending links found.")
        return

    print("🕵️ **Identity Review Required**")
    for link in links:
        pl_id, s_name, s_team, score, method, context, r_first, r_last, r_pos, r_team = link
        
        print(f"\n--- ID: {pl_id} ---")
        print(f"Source: {s_name} ({s_team or 'Unknown Team'}) [{method}: {score:.2f}]")
        print(f"Candidate: {r_first} {r_last} ({r_pos}, {r_team})")
        print(f"Context: \"{context or 'No context available'}\"")
        print(f"Action: `/link {pl_id} approve` or `/link {pl_id} reject`")

if __name__ == "__main__":
    asyncio.run(main())
