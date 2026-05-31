import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
    """
The history of Admiral Yi Sun-sin (이순신), the legendary Korean naval commander
of the Joseon Dynasty who defended Korea against Japanese invasions during the
Imjin War (1592-1598). Show his rise as a naval officer, the invention and
deployment of the iron-clad turtle ship (Geobukseon), and his most famous
victory at the Battle of Myeongnyang where he defeated over 300 Japanese ships
with only 13 Korean vessels. End with his heroic death at the Battle of Noryang.
"""
user_requirement = \
    """
Historical and educational tone for a general audience. Do not exceed 3 scenes.
Each scene should be no more than 4 shots. Include Korean cultural and naval
details (Joseon-era armor, turtle ship, Korean coastline).
"""
style = "Cinematic historical epic, realistic, dramatic lighting"


async def main():
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video.yaml")
    await pipeline(idea=idea, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
