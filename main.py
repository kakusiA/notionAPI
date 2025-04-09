import os
import requests
import openai
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
# 환경변수에서 API 키 및 데이터베이스 ID를 불러오거나 직접 코드에 입력합니다.
NOTION_SECRET = os.getenv("NOTION_SECRET")
NOTION_VERSION = os.getenv("NOTION_VERSION")  # 최신 Notion API 버전을 사용
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# OPENAI_API_KEY는 실제 API 키를 입력하세요.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    data = {}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print("Notion 데이터베이스 조회 실패:", response.text)
        return []
    return response.json().get("results", [])


def get_page_content_blocks(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"페이지({page_id}) 블록 조회 실패:", response.text)
        return []
    return response.json().get("results", [])


def extract_text_from_blocks(blocks):
    text_content = ""
    for block in blocks:
        if block.get("type") == "paragraph":
            for rich_text in block["paragraph"].get("rich_text", []):
                text_content += rich_text.get("plain_text", "") + " "
            text_content += "\n"
    return text_content


def generate_summary_chat(text):
    messages = [
        {"role": "system", "content": "너는 도움이 되는 정리 생성기로 행동해."},
        {"role": "user", "content": f"다음 텍스트를 노션에 올릴 수 있게 정리해줘:\n\n{text}"}
    ]
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.5,
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print("요약 생성 중 오류 발생:", e)
        return None


def create_summary_page(children_blocks):
    """
    한 번에 많은 blocks를 집어넣어 새 페이지를 생성합니다.
    """
    # 오늘 날짜 + "정리" 로 제목
    today_str = datetime.today().strftime("%Y-%m-%d")
    title = f"{today_str} 정리"

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "이름": {
                "title": [
                    {"text": {"content": title}}
                ]
            }
        },
        "children": children_blocks
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print("페이지 생성 실패:", response.text)
        return None

    new_page_id = response.json().get("id")
    print("새 요약 페이지 생성 성공:", new_page_id)
    return new_page_id


def process_pages():
    pages = get_notion_pages()
    if not pages:
        print("조회된 페이지가 없습니다.")
        return

    # 모든 요약을 모아둘 children 블록 배열
    children_blocks = []

    for page in pages:
        page_id = page.get("id")
        # 원본 페이지의 제목 추출
        title_info = page.get("properties", {}).get("이름", {}).get("title", [])
        original_title = "".join([t.get("plain_text", "") for t in title_info])

        print(f"페이지 처리 시작: {page_id} / 제목: {original_title}")

        blocks = get_page_content_blocks(page_id)
        if not blocks:
            print(f"페이지({page_id})에 블록이 없습니다.")
            continue

        text = extract_text_from_blocks(blocks)
        if not text.strip():
            print(f"페이지({page_id})에 추출할 텍스트가 없습니다.")
            continue

        summary = generate_summary_chat(text)
        if summary:
            print(f"[{original_title}] 요약 결과:\n", summary, "\n")

            # 1) 원본 페이지 제목을 Heading_2 블록으로 추가
            heading_block = {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": original_title}
                        }
                    ]
                }
            }

            # 2) 요약을 Paragraph 블록으로 추가
            paragraph_block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": summary}
                        }
                    ]
                }
            }

            children_blocks.append(heading_block)
            children_blocks.append(paragraph_block)

    # 한 번이라도 요약이 생성되었다면 새 요약 페이지를 만든다
    if children_blocks:
        create_summary_page(children_blocks)
    else:
        print("생성된 요약이 없어서 새 페이지를 만들지 않습니다.")


if __name__ == "__main__":
    process_pages()
