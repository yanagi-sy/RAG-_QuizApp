# API設計書

# API設計書 v1.0

## 0. 目的
- フロント（Next.js）とバック（FastAPI）の役割・I/Fを明確にし、実装を分離する

## 1. 共通仕様

### 1.1 Base URL（開発）
- `http://localhost:8000`

### 1.2 Header
- `Content-Type: application/json`

### 1.3 引用（citations）
- 役割：根拠をユーザーに提示する（最大5件）

例：
```json
{
  "source": "manual.pdf",
  "page": 3,
  "quote": "最初にAを実行する。"
}
1.4 エラー共通レスポンス
フロントが「入力修正」「再試行」「再出題」を判断できる形に統一する。

json
コードをコピーする
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "質問を入力してください"
  }
}
code（例）：

INVALID_INPUT：入力不備

NOT_FOUND：対象が見つからない（quiz_id不正/消失）

TIMEOUT：タイムアウト

INTERNAL_ERROR：想定外エラー

NETWORK_ERROR：接続不可（フロント側で生成される場合あり）

1.5 ハイブリッド検索比率（QAのみ、任意）
QA画面で意味検索↔キーワード検索の比率を調整する

送信されない場合はサーバ既定値を使用

json
コードをコピーする
{
  "retrieval": {
    "semantic": 0.7,
    "keyword": 0.3
  }
}
2. API一覧
API名	Method	Path	用途
Health	GET	/health	起動確認
Ask	POST	/ask	QA：質問→回答＋引用
QuizGenerate	POST	/quiz	クイズ：難易度→問題（quiz_id付き）
QuizJudge	POST	/judge	クイズ：回答→正誤＋解説＋引用

3. Health
3.1 Endpoint
GET /health

3.2 Response（成功）
json
コードをコピーする
{ "status": "ok" }
4. Ask（質問応答）
4.1 Endpoint
POST /ask

4.2 Request（例）
json
コードをコピーする
{
  "question": "この作業の手順は？",
  "retrieval": { "semantic": 0.7, "keyword": 0.3 }
}
4.3 Response（成功）
json
コードをコピーする
{
  "answer": "手順は次の通りです。まずAを行い、次にBを行います。",
  "citations": [
    { "source": "manual.pdf", "page": 3, "quote": "Aを実行した後にBを実行する。" }
  ]
}
4.4 Error（例：INVALID_INPUT）
json
コードをコピーする
{
  "error": { "code": "INVALID_INPUT", "message": "質問を入力してください" }
}
5. QuizGenerate（クイズ生成）
5.1 Endpoint
POST /quiz

5.2 Request（例）
json
コードをコピーする
{ "level": "beginner" }
level：

beginner / intermediate / advanced

5.3 Response（成功）
出題時点では「問題文のみ」を表示するため、正解・引用は返さない（内部保持）

json
コードをコピーする
{
  "quiz_id": "6b8f2f7e-2a44-4f8c-9e7e-9c8b6c8b2c1a",
  "question": "○×：最初にAを実行する。"
}
6. QuizJudge（クイズ判定）
6.1 Endpoint
POST /judge

6.2 Request（例）
フロントは○/×ボタン選択式

APIは boolean で統一（true=○、false=×）

json
コードをコピーする
{
  "quiz_id": "6b8f2f7e-2a44-4f8c-9e7e-9c8b6c8b2c1a",
  "answer": true
}
6.3 Response（成功）
json
コードをコピーする
{
  "is_correct": true,
  "correct_answer": true,
  "explanation": "マニュアルにはAを最初に行うと書かれているため○です。",
  "citations": [
    { "source": "manual.pdf", "page": 3, "quote": "最初にAを実行する。" }
  ]
}
6.4 Error（例：NOT_FOUND）
json
コードをコピーする
{
  "error": {
    "code": "NOT_FOUND",
    "message": "クイズ情報が見つかりません。再出題してください。"
  }
}
7. フロントでの呼び出し順
7.1 QA画面
質問入力 → POST /ask

返ってきた answer / citations を表示

7.2 クイズ画面
難易度選択 → POST /quiz

quiz_id を保持し、question を表示

○/×ボタン → POST /judge（quiz_id + answer）

is_correct / explanation / citations を表示
