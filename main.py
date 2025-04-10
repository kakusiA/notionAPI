import os
import json
import requests
import openai
import base64
from datetime import datetime
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 환경 변수
NOTION_SECRET = os.getenv("NOTION_SECRET")
NOTION_VERSION = os.getenv("NOTION_VERSION")  # 예: "2022-06-28"
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
GPT_MODEL = os.getenv("GPT_MODEL")

# GitHub 관련 환경 변수
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # 예: "username/repository-name"


def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json={})
    if response.status_code != 200:
        print("Notion 데이터베이스 조회 실패:", response.text)
        return []
    return response.json().get("results", [])


def update_page_status(page_id, status_name="완료"):
    """
    Notion 페이지의 '상태' 속성을 업데이트합니다.
    status_name: Notion 데이터베이스에서 사용하는 status 값 (예: "완료")
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    data = {
        "properties": {
            "상태": {
                "status": {
                    "name": status_name
                }
            }
        }
    }
    resp = requests.patch(url, headers=headers, json=data)
    if resp.status_code == 200:
        print(f"페이지({page_id}) 상태를 '{status_name}'로 업데이트했습니다.")
    else:
        print(f"페이지({page_id}) 상태 업데이트 실패:", resp.text)

def get_notion_page(page_id):
    """
    단일 Notion 페이지의 메타데이터를 가져옵니다.
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_SECRET}",
        "Notion-Version": NOTION_VERSION,
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"페이지({page_id}) 조회 실패:", resp.text)
        return None
    return resp.json()

def get_page_content_blocks(page_id):
    blocks = []
    next_cursor = None
    while True:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        headers = {
            "Authorization": f"Bearer {NOTION_SECRET}",
            "Notion-Version": NOTION_VERSION,
        }
        params = {"start_cursor": next_cursor} if next_cursor else {}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"페이지({page_id}) 블록 조회 실패:", response.text)
            break
        data = response.json()
        blocks.extend(data.get("results", []))
        if data.get("has_more"):
            next_cursor = data.get("next_cursor")
        else:
            break
    return blocks


def get_child_blocks(block_id):
    blocks = []
    next_cursor = None
    while True:
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
        headers = {
            "Authorization": f"Bearer {NOTION_SECRET}",
            "Notion-Version": NOTION_VERSION,
        }
        params = {"start_cursor": next_cursor} if next_cursor else {}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"하위 블록({block_id}) 조회 실패:", response.text)
            break
        data = response.json()
        blocks.extend(data.get("results", []))
        if data.get("has_more"):
            next_cursor = data.get("next_cursor")
        else:
            break
    return blocks


def extract_text_from_blocks(blocks, depth=0):
    """
    Notion 블록 리스트를 순회하며 텍스트와 코드 블록을
    마크다운 형식의 문자열 리스트로 변환합니다.
    코드 블록 앞뒤로 빈 줄을 추가해 블로그 렌더러 호환성을 높였습니다.
    """
    lines = []

    for blk in blocks:
        block_type = blk.get("type")
        block_value = blk.get(block_type, {})

        # 1) 코드 블록 처리: 앞뒤로 빈 줄 추가
        if block_type == "code":
            code_text = "".join(rt.get("plain_text", "") for rt in block_value.get("rich_text", []))
            # 코드 블록 전 빈 줄
            lines.append("")
            # ```language
            language = block_value.get("language", "")
            lines.append(f"```{language}")
            # 실제 코드 내용
            lines.extend(code_text.splitlines())
            # ```
            lines.append("```")
            # 코드 블록 후 빈 줄
            lines.append("")
            continue

        # 2) 일반 텍스트 (헤딩, 리스트, 문단)
        if "rich_text" in block_value and block_value["rich_text"]:
            # 텍스트 추출
            text = "".join(rt.get("plain_text", "") for rt in block_value["rich_text"])

            # 헤딩 처리
            prefix = ""
            if block_type.startswith("heading_"):
                level = int(block_type.split("_")[1])
                prefix = "#" * level + " "
            # 불릿 리스트
            elif block_type == "bulleted_list_item":
                prefix = "- "
            # 번호 리스트
            elif block_type == "numbered_list_item":
                prefix = "1. "

            # 깊이에 따른 들여쓰기
            indent = "  " * depth
            lines.append(f"{indent}{prefix}{text}")

        # 3) 자식 블록 재귀 처리
        if blk.get("has_children"):
            child_blocks = get_child_blocks(blk["id"])
            lines += extract_text_from_blocks(child_blocks, depth + 1)

    return lines



def save_blocks_to_json(blocks, filename="blocks_dump.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    print(f"블록 데이터가 '{filename}' 파일로 저장되었습니다.")


def generate_simple_summary(text, max_length=300):
    messages = [
        {"role": "system", "content": "너는 뛰어난 요약 전문가야. 주어진 텍스트의 핵심 내용을 100자 내외로 간결하게 요약해줘."},
        {"role": "user", "content": text}
    ]
    try:
        response = openai.ChatCompletion.create(
            model=GPT_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.5
        )
        summary = response.choices[0].message.content.strip()
        if len(summary) > max_length:
            summary = summary[:max_length].rsplit(" ", 1)[0] + "..."
        return summary
    except Exception as e:
        print("요약 생성 중 오류 발생:", e)
        text = text.strip().replace("\n", " ")
        if len(text) > max_length:
            return text[:max_length].rsplit(" ", 1)[0] + "..."
        return text


def split_text_into_chunks(text, max_length=2000):
    words = text.split()
    chunks = []
    current_chunk = ""
    for word in words:
        if len(current_chunk) + len(word) + 1 > max_length:
            chunks.append(current_chunk)
            current_chunk = word
        else:
            current_chunk = f"{current_chunk} {word}" if current_chunk else word
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def upload_blog_post_to_github(markdown_content, filename,page_id):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GitHub 토큰 또는 저장소 정보가 없습니다.")
        return None

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    commit_message = f"Add new blog post: {filename}"
    content_base64 = base64.b64encode(markdown_content.encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    get_response = requests.get(url, headers=headers)
    if get_response.status_code == 200:
        sha = get_response.json().get("sha")
        data = {"message": commit_message, "content": content_base64, "sha": sha}
    elif get_response.status_code == 404:
        data = {"message": commit_message, "content": content_base64}
    else:
        print("파일 존재 여부 확인 중 오류:", get_response.text)
        return None

    put_response = requests.put(url, headers=headers, json=data)
    if put_response.status_code in [200, 201]:
        print("GitHub 블로그 포스트 업로드 성공:", filename)

        return put_response.json()
    else:
        print("GitHub 블로그 포스트 업로드 실패:", put_response.text)
        return None



def process_page(page_id):
    # Notion에서 단일 페이지 정보 가져오기
    page = get_notion_page(page_id)
    if not page:
        print(f"페이지({page_id})를 찾을 수 없습니다.")
        return

    status = page.get("properties", {}).get("상태", {}).get("status", {}).get("name")
    # 완료되었거나 시작 전인 페이지는 건너뜀
    if status in ("완료", "시작 전"):
        print(f"페이지({page_id}) 상태가 '{status}'이므로 스킵합니다.")
        return

    title_info = page.get("properties", {}).get("이름", {}).get("title", [])
    original_title = "".join([t.get("plain_text", "") for t in title_info])
    print(f"페이지 처리 시작: {page_id} / 제목: {original_title}")

    # 페이지 블록 가져오기
    blocks = get_page_content_blocks(page_id)
    if not blocks:
        print(f"페이지({page_id})에 블록이 없습니다.")
        return

    # 텍스트 추출
    lines = extract_text_from_blocks(blocks)
    full_text = "\n".join(lines).strip()
    if not full_text:
        print(f"페이지({page_id})에 추출할 텍스트가 없습니다.")
        return

    # 요약 생성 (실제 함수로 교체)
    # simple_summary = generate_simple_summary(full_text)
    simple_summary = "객체지향 공부"
    print(f"[{original_title}] 간단 요약: {simple_summary}")

    # Markdown 본문 조립
    md_content = []
    md_content.append(f"## {original_title}\n")
    md_content.append(f"**요약:** {simple_summary}\n")
    md_content.append(full_text + "\n")
    md_content_body = "\n".join(md_content)

    # GitHub 업로드
    today = datetime.today()
    datetime_slug = today.strftime("%Y-%m-%d")
    datetime_str = today.strftime("%Y-%m-%d %H:%M:%S")
    post_title = original_title
    slug = original_title.replace(" ", "-")
    front_matter = (
        f"---\n"
        f"layout: post\n"
        f"title: \"{post_title}\"\n"
        f"date: {datetime_str}\n"
        f"---\n\n"
    )
    markdown_post = front_matter + md_content_body
    filename = f"_posts/{datetime_slug}-{slug}.md"
    upload_blog_post_to_github(markdown_post, filename, page_id)

    # 상태 업데이트
    if status == "배포전":
        update_page_status(page_id, "완료")
    print(f"페이지({page_id}) 처리 완료: GitHub 업로드 및 Notion 상태 업데이트 완료.")


def process_pages():
    pages = get_notion_pages()
    if not pages:
        print("조회된 페이지가 없습니다.")
        return

    for page in pages:
        process_page(page["id"])


if __name__ == "__main__":
    process_pages()
