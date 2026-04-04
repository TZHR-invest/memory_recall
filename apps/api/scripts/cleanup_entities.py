#!/usr/bin/env python3
"""
实体表脏数据清理脚本

功能:
- 删除黑名单匹配的实体
- 删除文件路径格式实体
- 删除纯数值实体
- 删除过长/过短实体
- 提供预览模式 (dry-run)
- 创建备份文件
- 生成清理报告

用法:
    python cleanup_entities.py --dry-run           # 预览待删除实体
    python cleanup_entities.py --confirm           # 执行清理
    python cleanup_entities.py --backup-dir ./backups  # 指定备份目录
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


MEANINGLESS_ENTITIES = {
    # 代词
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "自己",
    "大家",
    # 身份称谓
    "用户",
    "说话者",
    "作者",
    "读者",
    "需求方",
    # 时间词
    "目前",
    "平时",
    "最近",
    "现在",
    "当前",
    "近期",
    "将来",
    "过去",
    # 数量词
    "一个",
    "几个",
    "一些",
    "很多",
    "少量",
    "多个",
    "各种",
    "所有",
    # 副词
    "就",
    "也",
    "都",
    "还",
    "又",
    "才",
    "只",
    "最",
    "很",
    "非常",
    # 泛指名词 - 第一批
    "代码",
    "技术",
    "日志",
    "数据库",
    "系统",
    "项目",
    "功能",
    "服务",
    "接口",
    "模块",
    "组件",
    "文件",
    "配置",
    "数据",
    "信息",
    "内容",
    "问题",
    "方案",
    "方法",
    "方式",
    "模式",
    "架构",
    "设计",
    "实现",
    # 泛指名词 - 第二批（新增）
    "代码库",
    "前端",
    "后端",
    "按钮",
    "技能",
    "商店",
    "成本",
    "金钱",
    "利率",
    "新架构",
    "旧架构",
    "测试文件",
    "测试记忆",
    # 语言标识
    "中文",
    "英文",
    "英文版",
    "中文版",
    "EN",
    "CN",
    # 状态词
    "中断",
    "新建",
    "关联",
    "修正",
    "延后",
    "完成",
    "进行中",
    "待处理",
    # 平台/应用
    "博客",
    "微信",
    "微博",
    "网站",
    "app",
    "APP",
    # 技术缩写
    "AI",
    "UI",
    "API",
    "llm",
    "LLM",
    "git",
    "Git",
    # 抽象概念（新增）
    "偏好",
    "标题",
    "索引",
    "永久性个人事实",
    "明确要求",
    "临时任务",
    "一次性请求",
    "助手行为",
    "对话填充词",
    "有价值的上下文",
    "饮食偏好",
    # 技术术语（新增）
    "container_tag",
    "content_hash",
    "embedding",
    "keyId",
    "title",
    "url",
    "vector",
    "src",
    # 模式名称
    "add mode",
    "import-docs mode",
    # 第四轮清理 - 技术编号
    "技术1",
    "技术2",
    "技术3",
    # 第四轮清理 - 废弃/冗余
    "废弃服务",
    "废弃服务文件",
    "已删除的废弃服务文件",
    # 第四轮清理 - 泛指描述
    "长期项目",
    "项目文档",
    "项目记忆",
    "项目隔离功能",
    "工作地点",
    "实体提取",
    "去重逻辑",
    "语义去重阈值",
    # 第四轮清理 - 数值/价格
    "初始资金",
    "初始金钱",
    "单抽价格",
    "卡包价格",
    "升级费用",
    "升级到等级8的费用",
    # 第四轮清理 - 游戏机制
    "展示位上限",
    "展示损坏概率",
    "展示损坏系统",
    "满级禁用",
    "金钱不足禁用",
    "双升级系统",
    "双图谱召回",
    "统一召回系统",
    "库存等级系统",
    "玩家等级系统",
    "后台分析任务",
    "商店系统",
    "成就系统",
    "组合奖励系统",
    # 第四轮清理 - 卡牌稀有度
    "传说卡",
    "史诗卡",
    "普通卡",
    "稀有卡",
    "特典卡",
    "神话卡",
    "天罡星",
    "地煞星",
    # 第四轮清理 - 其他
    "主对话agent",
    "插件记忆召回功能",
    "Session 开始注入",
    "记忆提取规则",
    "游戏核心系统架构",
    "休闲小游戏",
    "水浒卡牌收集Web单机游戏",
}

SKIP_ENTITY_TYPES = {"time", "number", "activity"}


def should_skip_entity(name: str) -> bool:
    if not name:
        return True
    name = name.strip()
    if len(name) < 2 or len(name) > 20:
        return True
    if re.match(r"^[\d.]+$", name):
        return True
    if re.match(r"^[a-zA-Z0-9_\-./]+$", name):
        if "/" in name or name.count(".") > 1:
            return True
    if re.match(r"^[\w.]+:\d+", name):
        return True
    if re.match(r"^v?\d+\.\d+(\.\d+)?", name.lower()):
        return True
    if re.match(r"^\d+端口$", name):
        return True
    if re.match(r"^(bg_)?[a-f0-9]{6,}$", name.lower()):
        return True
    if re.match(r"^/\w+", name):
        return True
    if re.search(r"(表|字段|端点|配置|方法|函数|参数)$", name):
        return True
    if re.match(r"^[a-zA-Z_]+\(\)$", name):
        return True
    if re.search(r"(bug|错误|问题)$", name):
        return True
    if re.match(r"^[#*\-\|]+\s*", name):
        return True
    if re.search(r"\|\s*\d", name):
        return True
    # 第四轮清理 - 新增规则
    if re.search(r"系统$", name):
        return True
    if re.search(r"价格$", name):
        return True
    if re.search(r"费用$", name):
        return True
    if re.search(r"概率$", name):
        return True
    if re.search(r"阈值$", name):
        return True
    if re.search(r"机制$", name):
        return True
    if re.search(r"规则$", name):
        return True
    if re.search(r"服务$", name):
        return True
    if re.match(r"^技术\d+$", name):
        return True
    if re.match(r"^项目", name):
        return True
    if re.match(r"^迁移", name):
        return True
    if re.match(r"(?i)^migration", name):
        return True
    if re.match(r"^\d+.*抽$", name):
        return True
    if re.match(r"^\d+张.*卡牌$", name):
        return True
    if re.match(r"^(传说|史诗|普通|稀有|特典|神话)卡$", name):
        return True
    if re.match(r"^(天罡|地煞)星$", name):
        return True
    return False


async def get_entity_stats() -> Dict[str, Any]:
    total = await db.fetchval("SELECT COUNT(*) FROM entities")
    by_type = await db.fetch(
        "SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY count DESC"
    )
    return {"total": total, "by_type": {row["type"]: row["count"] for row in by_type}}


async def find_blacklist_entities() -> List[Dict[str, Any]]:
    placeholders = ", ".join(f"'{name}'" for name in MEANINGLESS_ENTITIES)
    query = f"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE LOWER(TRIM(name)) IN ({placeholders})
        ORDER BY name
    """
    return await db.fetch(query)


async def find_file_path_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^[a-zA-Z0-9_\\-./]+$'
          AND (name LIKE '%/%' OR name ~ '\\.[a-z]{2,4}$')
        ORDER BY name
    """
    return await db.fetch(query)


async def find_numeric_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^[0-9.]+$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_length_invalid_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE LENGTH(name) < 2 OR LENGTH(name) > 20
        ORDER BY LENGTH(name) DESC
    """
    return await db.fetch(query)


async def find_table_field_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '(表|字段|端点|配置|方法|函数|参数)$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_version_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^v?[0-9]+\\.[0-9]+(\\.[0-9]+)?'
           OR name ~ '[0-9]+\\.[0-9]+版本'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_random_id_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^(bg_)?[a-f0-9]{6,}$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_bug_problem_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~* '(bug|错误|问题)$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_format_invalid_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^[#*\-\|]+\s*'
           OR name ~ '\|\s*\d'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_duplicate_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, name, ROW_NUMBER() OVER (PARTITION BY name ORDER BY mention_count DESC, id) as rn
                FROM entities
            ) ranked
            WHERE rn = 1
        )
        AND name IN (
            SELECT name FROM entities GROUP BY name HAVING COUNT(*) > 1
        )
        ORDER BY name, id
    """
    return await db.fetch(query)


async def find_invalid_person_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE type = 'person'
        AND (
            name ~ '[#\*\-\|]'
            OR name ~ '\|\s*\d'
            OR name ~ '^[#\-\*]+\s*'
            OR name ~ '^(将\s*\|)'
            OR name = '史诗'
            OR name = '天罡'
            OR name = '地煞'
            OR name LIKE '%游戏%'
            OR name LIKE '%用户%'
            OR name LIKE '%文档%'
        )
        ORDER BY name
    """
    return await db.fetch(query)


async def find_system_suffix_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '系统$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_price_cost_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '(价格|费用)$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_probability_threshold_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '(概率|阈值)$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_migration_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^迁移'
           OR name ~* '^migration'
           OR name ~ '迁移.*\d'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_technical_number_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^技术\d+$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_card_rarity_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^(传说|史诗|普通|稀有|特典|神话)卡$'
           OR name ~ '^(天罡|地煞)星$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_draw_count_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^\d+.*抽$'
           OR name ~ '^\d+张.*卡牌$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_invalid_preference_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE type = 'preference'
        AND (
            name LIKE '%卡牌%'
            OR name LIKE '%游戏%'
            OR name LIKE '%开发%'
            OR name LIKE '%测试%'
            OR name LIKE '%整洁%'
        )
        ORDER BY name
    """
    return await db.fetch(query)


async def find_invalid_event_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE type = 'event'
        AND (
            name LIKE '%配置项%'
            OR name LIKE '%机制%'
            OR name LIKE '%通过率%'
            OR name LIKE '%清理%'
            OR name LIKE '%修复%'
            OR name LIKE '%测试%'
        )
        ORDER BY name
    """
    return await db.fetch(query)


async def find_invalid_organization_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE type = 'organization'
        AND (
            name LIKE '%agent%'
            OR name LIKE '%仓库%'
            OR name = 'Kimi'
        )
        ORDER BY name
    """
    return await db.fetch(query)


async def find_invalid_location_entities() -> List[Dict[str, Any]]:
    query = r"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE type = 'location'
        AND (
            name = 'Google'
            OR name = 'Supermemory'
            OR name LIKE '%仓库%'
        )
        ORDER BY name
    """
    return await db.fetch(query)


async def delete_entities(entity_ids: List[str]) -> int:
    if not entity_ids:
        return 0

    placeholders = ", ".join(f"'{eid}'" for eid in entity_ids)

    await db.execute(f"DELETE FROM memory_entities WHERE entity_id IN ({placeholders})")
    await db.execute(
        f"DELETE FROM entity_relations WHERE from_entity_id IN ({placeholders}) OR to_entity_id IN ({placeholders})"
    )

    result = await db.execute(f"DELETE FROM entities WHERE id IN ({placeholders})")
    return int(result.split()[-1]) if result else 0


async def create_backup(backup_dir: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"entities_backup_{timestamp}.sql")

    os.makedirs(backup_dir, exist_ok=True)

    entities = await db.fetch("SELECT * FROM entities")
    memory_entities = await db.fetch("SELECT * FROM memory_entities")
    entity_relations = await db.fetch("SELECT * FROM entity_relations")

    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(f"-- Entity Backup created at {datetime.now().isoformat()}\n\n")

        f.write("-- Entities\n")
        for row in entities:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO entities VALUES ({', '.join(values)});\n")

        f.write("\n-- Memory Entities\n")
        for row in memory_entities:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO memory_entities VALUES ({', '.join(values)});\n")

        f.write("\n-- Entity Relations\n")
        for row in entity_relations:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO entity_relations VALUES ({', '.join(values)});\n")

    return backup_file


def print_report(before_stats: Dict, after_stats: Dict, deleted_counts: Dict):
    print("\n" + "=" * 60)
    print("实体清理报告")
    print("=" * 60)

    print(f"\n清理前总数: {before_stats['total']}")
    print(f"清理后总数: {after_stats['total']}")
    print(f"总计删除: {before_stats['total'] - after_stats['total']}")

    print("\n按类型统计:")
    print(f"{'类型':<15} {'清理前':>10} {'清理后':>10} {'删除':>10}")
    print("-" * 50)

    all_types = set(before_stats["by_type"].keys()) | set(after_stats["by_type"].keys())
    for entity_type in sorted(all_types):
        before = before_stats["by_type"].get(entity_type, 0)
        after = after_stats["by_type"].get(entity_type, 0)
        deleted = before - after
        print(f"{entity_type:<15} {before:>10} {after:>10} {deleted:>10}")

    print("\n删除分类统计:")
    for category, count in deleted_counts.items():
        print(f"  {category}: {count}")


def print_preview(category: str, entities: List[Dict[str, Any]], limit: int = 20):
    print(f"\n{category} ({len(entities)} 条):")
    print("-" * 80)

    for i, entity in enumerate(entities[:limit]):
        print(
            f"  [{entity['id']}] {entity['name']} ({entity['type']}) - {entity['container_tag'][:30]}"
        )

    if len(entities) > limit:
        print(f"  ... 还有 {len(entities) - limit} 条")


async def main():
    parser = argparse.ArgumentParser(description="实体表脏数据清理脚本")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不执行删除")
    parser.add_argument("--confirm", action="store_true", help="确认执行清理")
    parser.add_argument("--backup-dir", default="./backups", help="备份目录")

    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print("错误: 必须指定 --dry-run 或 --confirm")
        print("\n用法:")
        print("  python cleanup_entities.py --dry-run    # 预览待删除实体")
        print("  python cleanup_entities.py --confirm    # 执行清理")
        sys.exit(1)

    print("=" * 60)
    print("实体表脏数据清理")
    print("=" * 60)

    before_stats = await get_entity_stats()
    print(f"\n当前实体总数: {before_stats['total']}")

    blacklist_entities = await find_blacklist_entities()
    file_path_entities = await find_file_path_entities()
    numeric_entities = await find_numeric_entities()
    length_invalid_entities = await find_length_invalid_entities()
    table_field_entities = await find_table_field_entities()
    version_entities = await find_version_entities()
    random_id_entities = await find_random_id_entities()
    bug_problem_entities = await find_bug_problem_entities()
    format_invalid_entities = await find_format_invalid_entities()
    duplicate_entities = await find_duplicate_entities()
    invalid_person_entities = await find_invalid_person_entities()
    # 第四轮清理 - 新增查询
    system_suffix_entities = await find_system_suffix_entities()
    price_cost_entities = await find_price_cost_entities()
    probability_threshold_entities = await find_probability_threshold_entities()
    migration_entities = await find_migration_entities()
    technical_number_entities = await find_technical_number_entities()
    card_rarity_entities = await find_card_rarity_entities()
    draw_count_entities = await find_draw_count_entities()
    invalid_preference_entities = await find_invalid_preference_entities()
    invalid_event_entities = await find_invalid_event_entities()
    invalid_organization_entities = await find_invalid_organization_entities()
    invalid_location_entities = await find_invalid_location_entities()

    all_entity_ids = set()
    for entities in [
        blacklist_entities,
        file_path_entities,
        numeric_entities,
        length_invalid_entities,
        table_field_entities,
        version_entities,
        random_id_entities,
        bug_problem_entities,
        format_invalid_entities,
        duplicate_entities,
        invalid_person_entities,
        # 第四轮清理 - 新增
        system_suffix_entities,
        price_cost_entities,
        probability_threshold_entities,
        migration_entities,
        technical_number_entities,
        card_rarity_entities,
        draw_count_entities,
        invalid_preference_entities,
        invalid_event_entities,
        invalid_organization_entities,
        invalid_location_entities,
    ]:
        for entity in entities:
            all_entity_ids.add(str(entity["id"]))

    print(f"\n待删除实体总数: {len(all_entity_ids)}")

    if args.dry_run:
        print("\n【预览模式】以下实体将被删除:")
        print_preview("黑名单实体", blacklist_entities)
        print_preview("文件路径实体", file_path_entities)
        print_preview("纯数值实体", numeric_entities)
        print_preview("长度异常实体", length_invalid_entities)
        print_preview("表名/字段名实体", table_field_entities)
        print_preview("版本号实体", version_entities)
        print_preview("随机ID实体", random_id_entities)
        print_preview("Bug/问题实体", bug_problem_entities)
        print_preview("格式错误实体", format_invalid_entities)
        print_preview("重复实体(保留首次)", duplicate_entities)
        print_preview("无效person实体", invalid_person_entities)
        # 第四轮清理 - 新增预览
        print_preview("系统后缀实体", system_suffix_entities)
        print_preview("价格/费用实体", price_cost_entities)
        print_preview("概率/阈值实体", probability_threshold_entities)
        print_preview("迁移相关实体", migration_entities)
        print_preview("技术编号实体", technical_number_entities)
        print_preview("卡牌稀有度实体", card_rarity_entities)
        print_preview("抽卡数量实体", draw_count_entities)
        print_preview("无效preference实体", invalid_preference_entities)
        print_preview("无效event实体", invalid_event_entities)
        print_preview("无效organization实体", invalid_organization_entities)
        print_preview("无效location实体", invalid_location_entities)

        print(f"\n提示: 使用 --confirm 执行清理")

    elif args.confirm:
        backup_file = await create_backup(args.backup_dir)
        print(f"\n备份已创建: {backup_file}")

        print("\n确认删除 {} 个实体? [y/N]: ".format(len(all_entity_ids)), end="")
        confirmation = input().strip().lower()

        if confirmation != "y":
            print("已取消清理")
            sys.exit(0)

        print("\n正在清理...")
        deleted_count = await delete_entities(list(all_entity_ids))

        after_stats = await get_entity_stats()

        deleted_counts = {
            "黑名单实体": len(blacklist_entities),
            "文件路径实体": len(file_path_entities),
            "纯数值实体": len(numeric_entities),
            "长度异常实体": len(length_invalid_entities),
            "表名/字段名实体": len(table_field_entities),
            "版本号实体": len(version_entities),
            "随机ID实体": len(random_id_entities),
            "Bug/问题实体": len(bug_problem_entities),
            "格式错误实体": len(format_invalid_entities),
            "重复实体(保留首次)": len(duplicate_entities),
            "无效person实体": len(invalid_person_entities),
            # 第四轮清理 - 新增统计
            "系统后缀实体": len(system_suffix_entities),
            "价格/费用实体": len(price_cost_entities),
            "概率/阈值实体": len(probability_threshold_entities),
            "迁移相关实体": len(migration_entities),
            "技术编号实体": len(technical_number_entities),
            "卡牌稀有度实体": len(card_rarity_entities),
            "抽卡数量实体": len(draw_count_entities),
            "无效preference实体": len(invalid_preference_entities),
            "无效event实体": len(invalid_event_entities),
            "无效organization实体": len(invalid_organization_entities),
            "无效location实体": len(invalid_location_entities),
        }

        print_report(before_stats, after_stats, deleted_counts)
        print(f"\n清理完成! 共删除 {deleted_count} 个实体")


if __name__ == "__main__":
    asyncio.run(main())
