import anthropic
import json
import pandas as pd


ALL_COLUMNS = [
    "product_id", "product_title", "product_url", "date", "review_content",
    "review_score", "review_title", "display_name", "email",
    "md_customer_country", "published", "product_image_url",
    "product_description", "comment_content", "comment_public",
    "comment_created_at", "published_image_url", "unpublished_image_url",
    "published_video_url", "unpublished_video_url", "cf_Y__X",
]

COLUMN_MAPPING = {
    "sku": "product_id",
    "review": "review_content",
    "rating": "review_score",
    "author": "display_name",
    "date": "date",
    "extra": [
        "product_title", "product_url", "email", "md_customer_country",
        "published", "product_image_url", "product_description",
        "comment_content", "comment_public", "comment_created_at",
        "published_image_url", "unpublished_image_url", "published_video_url",
        "unpublished_video_url", "cf_Y__X", "review_title",
    ],
    "all_columns": ALL_COLUMNS,
}


def build_prompt(
    existing_reviews: list,
    num_reviews: int,
    review_type: str,
    diversity_level: str,
    already_generated: list,
    selling_points: str = "",
    product_id: str = "",
) -> str:
    sku_value = product_id or (existing_reviews[0].get("product_id", "Unknown") if existing_reviews else "Unknown")

    if review_type == "긍정":
        scored = sorted(existing_reviews, key=lambda r: -float(r.get("review_score", 0) or 0))
    else:
        scored = sorted(existing_reviews, key=lambda r: float(r.get("review_score", 5) or 5))
    examples = scored[:10]

    examples_simple = [
        {
            "review_content": r.get("review_content", ""),
            "review_score": r.get("review_score", ""),
            "review_title": r.get("review_title", ""),
            "display_name": r.get("display_name", ""),
        }
        for r in examples
    ]
    examples_json = json.dumps(examples_simple, ensure_ascii=False, indent=2)

    if review_type == "긍정":
        tone_instruction = (
            "ポジティブなレビューを作成してください。評価は4または5のみ使用してください。"
            "実際に購入して満足した顧客のように、具体的な長所を自然に表現してください。"
        )
        rating_range = "4または5"
    else:
        tone_instruction = (
            "ネガティブなレビューを作成してください。評価は1または2のみ使用してください。"
            "過度に攻撃的にならず、失望した顧客や問題を経験した顧客のように自然に表現してください。"
            "商品のどの点が期待に応えられなかったかを具体的に述べてください。"
        )
        rating_range = "1または2"

    diversity_instruction = {
        "낮음": "既存レビューと似たトーンと長さを維持してください。",
        "보통": "既存レビューのパターンを参考にしつつ、表現と観点を多様に変えてください。",
        "높음": "既存レビューから商品特性のみ参考にし、まったく異なる文体と状況で創造的に作成してください。",
    }[diversity_level]

    already_section = ""
    if already_generated:
        prev = [
            {"review_content": r.get("review_content", ""), "review_title": r.get("review_title", "")}
            for r in already_generated[-5:]
        ]
        already_section = f"""
## 生成済みレビュー（重複禁止）
{json.dumps(prev, ensure_ascii=False, indent=2)}
"""

    appeal_section = ""
    if selling_points and selling_points.strip():
        appeal_section = f"""
## 訴求ポイント（必須反映）
以下の特徴・強みをレビューに自然に織り込んでください：
{selling_points}
"""

    product_fields = {}
    if existing_reviews:
        product_fields = {
            "product_title": existing_reviews[0].get("product_title", ""),
            "product_url": existing_reviews[0].get("product_url", ""),
            "product_image_url": existing_reviews[0].get("product_image_url", ""),
            "product_description": existing_reviews[0].get("product_description", ""),
        }

    output_schema = {
        "product_id": sku_value,
        "product_title": product_fields.get("product_title", ""),
        "product_url": product_fields.get("product_url", ""),
        "date": "YYYY-MM-DD",
        "review_content": "レビュー内容（日本語）",
        "review_score": rating_range,
        "review_title": "レビュータイトル（日本語）",
        "display_name": "名前 姓イニシャル（例: Carol S.）",
        "email": "cs@celladix.jp",
        "md_customer_country": "JP",
        "published": "true",
        "product_image_url": product_fields.get("product_image_url", ""),
        "product_description": product_fields.get("product_description", ""),
        "comment_content": "",
        "comment_public": "",
        "comment_created_at": "",
        "published_image_url": "",
        "unpublished_image_url": "",
        "published_video_url": "",
        "unpublished_video_url": "",
        "cf_Y__X": "",
    }

    existing_section = ""
    if existing_reviews:
        existing_section = f"""
## 既存レビュー（商品特性把握用の参考資料）
{examples_json}
"""
    else:
        existing_section = "\n## 既存レビュー\n既存レビューデータなし。訴求ポイントをもとに作成してください。\n"

    prompt = f"""あなたは実際のショッピングモールの顧客レビューを生成する専門家です。

## 作業
商品（product_id: {sku_value}）に関する新しいレビューを{num_reviews}件作成してください。
{existing_section}{appeal_section}{already_section}
## 生成ルール
1. **言語**: レビューの内容（review_content・review_title）は必ず日本語で作成してください。
2. **トーン**: {tone_instruction}
3. **多様性**: {diversity_instruction}
4. **重複禁止**: 生成する{num_reviews}件のレビューで内容が重複しないようにしてください。
5. **商品への忠実度**: 既存レビューや訴求ポイントに記載された実際の商品特性のみ使用してください。
6. **日付**: 直近1年以内の日付をランダムに割り振ってください（YYYY-MM-DD形式）。
7. **著者名**: 自然な日本人の名前（ひらがな・カタカナ・漢字）にしてください（例: 田中さくら、山本ゆい、佐藤あおい、鈴木みな）。既存レビューの著者名と重複しないようにしてください。
8. **メールアドレス**: 必ず `cs@celladix.jp` に統一してください。
9. **国コード**: 必ず `JP` に統一してください。
10. **評価**: 必ず{rating_range}のいずれかのみ使用してください。

## 出力形式
必ず以下のJSON配列形式のみで回答してください。説明テキストなしでJSONのみ出力：

[
  {json.dumps(output_schema, ensure_ascii=False)},
  ...
]
"""
    return prompt


def _parse_json_response(raw: str) -> list:
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("["):
                text = part
                break
    if not text.startswith("["):
        start = text.find("[")
        if start != -1:
            text = text[start:]
    return json.loads(text)


def generate_reviews_for_sku(
    existing_df: pd.DataFrame,
    num_reviews: int,
    review_type: str,
    diversity_level: str,
    api_key: str,
    selling_points: str = "",
    product_id: str = "",
) -> list:
    client = anthropic.Anthropic(api_key=api_key)
    existing_records = existing_df.to_dict(orient="records") if not existing_df.empty else []

    BATCH_SIZE = 15
    all_results = []
    remaining = num_reviews

    temperature_map = {"낮음": 0.7, "보통": 0.85, "높음": 1.0}
    temperature = temperature_map[diversity_level]

    while remaining > 0:
        batch_num = min(remaining, BATCH_SIZE)

        prompt = build_prompt(
            existing_records,
            batch_num,
            review_type,
            diversity_level,
            all_results,
            selling_points,
            product_id,
        )

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text
                batch_result = _parse_json_response(raw)
                all_results.extend(batch_result)
                break
            except Exception:
                if attempt == 2:
                    placeholder = {col: "" for col in ALL_COLUMNS}
                    placeholder["product_id"] = existing_records[0].get("product_id", "") if existing_records else ""
                    all_results.extend([placeholder] * batch_num)

        remaining -= batch_num

    return all_results[:num_reviews]
