from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.models import Experience


SEED_EXPERIENCES: tuple[dict[str, Any], ...] = (
    {
        "id": "00000000-0000-4000-8000-000000000501",
        "activity_name": "亲子共读活动",
        "contributor_name": "演示贡献者甲",
        "contributor_role": "社区阅读志愿者",
        "context": "亲子共读开始后，有几个第一次来的孩子一直站在门口，没有进入围坐区域。",
        "action_and_reason": "我把统一围坐改成自由选书，希望先降低他们参与的门槛。",
        "observed_result": "孩子后来走进来翻书，但现场变得比较分散。",
        "went_well": "原本停在门口的孩子开始接触活动材料。",
        "shortcomings": "自由选书后没有及时准备重新收拢大家的方法。",
        "things_to_note": "提前准备自由选择之后的收拢环节。",
        "open_question": None,
        "recorded_at": datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
    },
    {
        "id": "00000000-0000-4000-8000-000000000502",
        "activity_name": "亲子共读活动",
        "contributor_name": "演示贡献者乙",
        "contributor_role": "社区阅读志愿者",
        "context": "自由阅读结束时，孩子们仍分散在书架和地垫旁，听不到结束提示。",
        "action_and_reason": "我用固定的拍手节奏召集大家，并请家长一起把书放回展示桌。",
        "observed_result": "大部分孩子很快回到地垫，结束环节没有继续拖延。",
        "went_well": "简单重复的声音提示比临时提高音量更容易被注意到。",
        "shortcomings": "第一次提示前没有向新来的家庭说明这个信号。",
        "things_to_note": "活动开场时先示范一次结束信号。",
        "open_question": None,
        "recorded_at": datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
    },
    {
        "id": "00000000-0000-4000-8000-000000000503",
        "activity_name": "亲子共读活动",
        "contributor_name": "演示贡献者丙",
        "contributor_role": "社区阅读志愿者",
        "context": "提问环节总是同样几个年龄较大的孩子抢先回答，其他孩子没有开口。",
        "action_and_reason": "我改为先让每个家庭小声讨论，再邀请还没回答过的孩子分享。",
        "observed_result": "更多孩子表达了自己的观察，但活动时间比计划多了几分钟。",
        "went_well": "等待和家庭讨论给了慢热的孩子准备时间。",
        "shortcomings": "没有为增加的讨论时间调整后面的流程。",
        "things_to_note": "减少问题数量，为家庭讨论预留时间。",
        "open_question": None,
        "recorded_at": datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc),
    },
    {
        "id": "00000000-0000-4000-8000-000000000504",
        "activity_name": "绘本阅读分享",
        "contributor_name": "演示贡献者丁",
        "contributor_role": "图书馆活动协作者",
        "context": "分享开始前投影设备突然无法显示绘本页面。",
        "action_and_reason": "我改用纸质绘本在小组间传阅，并缩短每组观察的页面数量。",
        "observed_result": "活动按时开始，但后排参与者看细节比较困难。",
        "went_well": "纸质备份让活动没有因设备故障取消。",
        "shortcomings": "只准备了一本纸质绘本，传阅等待较长。",
        "things_to_note": "设备演示活动至少准备两份可传阅的纸质材料。",
        "open_question": None,
        "recorded_at": datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc),
    },
    {
        "id": "00000000-0000-4000-8000-000000000505",
        "activity_name": "儿童手工活动",
        "contributor_name": "演示贡献者戊",
        "contributor_role": "社区活动志愿者",
        "context": "剪贴材料集中放在一张桌上，孩子们排队等待并不断离开座位。",
        "action_and_reason": "我把材料拆成几个小盒分到各桌，减少集中领取。",
        "observed_result": "等待明显减少，但有两桌较早用完了彩纸。",
        "went_well": "分散材料让孩子能连续完成手工作品。",
        "shortcomings": "各桌材料数量没有按人数分配。",
        "things_to_note": "分盒前按桌人数清点常用材料并留一份机动补充。",
        "open_question": None,
        "recorded_at": datetime(2026, 7, 9, 9, 0, tzinfo=timezone.utc),
    },
    {
        "id": "00000000-0000-4000-8000-000000000506",
        "activity_name": "户外亲子游戏",
        "contributor_name": "演示贡献者己",
        "contributor_role": "社区活动志愿者",
        "context": "户外游戏进行到一半开始下雨，地面很快变滑。",
        "action_and_reason": "我停止奔跑游戏，把家庭带到有遮挡的走廊做静态配对任务。",
        "observed_result": "没有人继续在湿滑区域活动，但临时任务的材料不够。",
        "went_well": "及时停止原活动避免了在湿滑地面继续奔跑。",
        "shortcomings": "雨天替代任务只准备了少量卡片。",
        "things_to_note": "户外活动前准备无需大型材料的室内备用玩法。",
        "open_question": "怎样更快判断小雨是否需要立即转移？",
        "recorded_at": datetime(2026, 7, 11, 9, 0, tzinfo=timezone.utc),
    },
)


def seed_experiences(db: Session) -> int:
    seed_ids = [item["id"] for item in SEED_EXPERIENCES]
    existing_ids = set(
        db.scalars(select(Experience.id).where(Experience.id.in_(seed_ids)))
    )
    inserted = 0
    for item in SEED_EXPERIENCES:
        if item["id"] in existing_ids:
            continue
        db.add(Experience(**item, updated_at=item["recorded_at"]))
        inserted += 1
    db.commit()
    return inserted


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = build_engine(settings.database_url)
    try:
        Base.metadata.create_all(engine)
        factory = build_session_factory(engine)
        with factory() as db:
            inserted = seed_experiences(db)
        print(f"Seeded {inserted} new experiences.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
