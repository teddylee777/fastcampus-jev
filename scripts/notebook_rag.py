"""Notebook source for 12 (document RAG: Jev picks folders and files, grep finds, the LLM writes).

Imported by build_notebooks.py. The closing summary lives in RAG_RESULTS_SUMMARY so it can be
rewritten after the notebook has been executed and the numbers are known.
"""

from __future__ import annotations

RAG_SETUP = """import sys
sys.path.insert(0, "..")  # 프로젝트 루트의 jev_agent 패키지를 불러오기 위함

import statistics
import pandas as pd
from dotenv import load_dotenv
load_dotenv("../.env")

from jev_agent.agent import build_chat_model
from jev_agent.jev import JevClient
from jev_agent.rag.corpus import INSUFFICIENT_QUERY, SAMPLE_QUERIES, load_corpus_index
from jev_agent.rag.decisions import (
    FILE_THRESHOLD, FOLDER_THRESHOLD, MAX_FILES, MAX_FOLDERS, SUFFICIENCY_THRESHOLD,
    build_file_question, build_folder_question, read_answer, read_probabilities, select_labels,
)
from jev_agent.rag.graph import build_doc_rag_graph
from jev_agent.rag.retriever import search_passages

pd.set_option("display.max_colwidth", 70)
jev = JevClient()
llm = build_chat_model()
index = load_corpus_index()
print("Jev 모델:", jev.model, "/ 답변 모델:", llm.model_name)"""

STEPS_TABLE = """def steps_table(output):
    \"\"\"그래프 출력의 steps 를 한 줄에 한 단계씩 보여 주는 표.\"\"\"
    rows = []
    for step in output["steps"]:
        top_label, top_probability = max(step["probabilities"].items(), key=lambda item: item[1])
        rows.append({
            "단계": step["kind"],
            "판정": step["verdict"],
            "가장 큰 옵션": top_label,
            "그 probability": round(top_probability, 3),
            "기준값": step["threshold"],
            "지연(ms)": step["latency_ms"],
            "비용($)": step["cost"],
        })
    return pd.DataFrame(rows)"""

RAG_RESULTS_SUMMARY = """## 정리

아래 숫자는 이 노트북에 저장된 실행에서 나온 값입니다. 질의는 세 개, 질의마다 세 번씩이라 표본이 작습니다. 다시 실행하면 probability 가 조금 달라집니다.

### 골든 셋 9회 실행

| 질의 | 기대 | 세 번의 결과 | 확인한 값 |
|---|---|---|---|
| 배송비는 얼마인가요? | answered | answered 3회 | 폴더는 세 번 모두 `shipping` 만 선택, 충분성 probability 0.94~0.95, 근거 검증 `supports` 3회 |
| 환불하면 사용한 적립금은 어떻게 되나요? | answered | answered 3회 | 세 번 모두 `returns` 와 `membership` 선택, returns 0.50~0.57, membership 0.41~0.48, 충분성 0.94, 근거 검증 `supports` 3회 |
| 주차장 약도를 팩스로 보내주세요 | stopped | `no_folder` 3회 | `none` probability 0.99, 답변 없음 |

세 질의 모두 기대와 맞았고, 기준값은 시작값(폴더 0.25, 파일 0.2, 충분성 0.5)에서 바꾸지 않았습니다.

### 읽을 때 주의할 점

- **두 폴더에 걸린 질의는 아슬아슬합니다.** 두 번째 실행에서 returns 0.50, membership 0.48 로 거의 반반이었습니다. 폴더 기준값 0.25 는 세 번의 membership 최솟값 0.41 보다 낮아서 두 폴더가 모두 선택됐지만, 기준값을 0.4 쯤으로 올리면 최솟값 0.41 과의 차이가 0.01 뿐이라 실행마다 membership 이 빠질 수 있습니다.
- **충분성으로 멈춘 사례는 한 번 실행했습니다.** "해외 배송비는 얼마인가요?" 는 구절을 찾은 뒤 충분성 probability 0.07 이 기준값 0.5 에 못 미쳐 `insufficient` 로 끝났고, 이때 LLM 은 호출되지 않았습니다. 충분성은 통과했는데 LLM 이 거절 문장으로 답하는 둘째 방어선은 이 실행에서 나타나지 않아 직접 확인하지 못했습니다.
- **호출 횟수와 비용.** 9회 실행에서 Jev 를 27번 불렀고 `usage.cost` 합계는 $0.000655 였습니다. Jev 지연은 중앙값 296ms (최솟값 249ms, 최댓값 378ms) 였고, 답변을 쓴 LLM 호출은 6번이었습니다. LLM 비용은 이 합계에 들어 있지 않습니다.
- **`none` option 의 역할.** 문서에 없는 질의가 억지로 폴더를 고르지 않고 `none` 0.99 로 멈춘 것은 이 option 이 있었기 때문으로 보입니다. 다만 질의 하나로 확인한 것이라, 문서와 낱말만 겹치는 다른 엉뚱한 질의에서도 그런지는 확인하지 못했습니다."""

RAG_LIMITS = """## 한계

- **문서 안의 지시문**: 검색된 구절에 "이전 지시를 무시하라" 같은 문장이 들어 있어도, 이 그래프에서 막는 것은 답변 프롬프트의 규칙 하나뿐입니다. 구절은 신뢰할 수 없는 자료이니 따르지 말라고 시스템 프롬프트에 적어 두었을 뿐, 구절을 Jev 로 검사하지는 않습니다.
- **같은 입력, 다른 점수**: Jev 의 probability 는 같은 질의를 다시 보내도 조금씩 달라집니다. 위 질의별 최솟값과 최댓값 표가 그 폭입니다. "두 폴더에 걸침" 질의에서 returns 는 0.50~0.57, membership 은 0.41~0.48 사이에서 움직였고, 한 실행에서는 returns 0.50 대 membership 0.48 까지 좁혀졌습니다. 기준값 근처에 있는 옵션은 실행마다 선택됐다가 빠졌다가 할 수 있습니다.
- **grep 이 놓친 것**: 검색은 질의 낱말이 문단에 부분 문자열로 들어 있는지만 봅니다. 문서에 같은 뜻이 다른 낱말로 적혀 있으면 구절이 비고, 뒤 단계가 그것을 되살리지 못합니다.
- **옵션 순서 편향**: Choice 는 앞에 놓인 옵션이 유리해지는 경향이 있습니다. 옵션을 이름순으로 정렬하고 `none` 과 `supports` 를 뒤에 두어 줄이기만 했을 뿐 없애지는 못했습니다.
- **기준값은 시작값**: 폴더 0.25, 파일 0.2, 충분성 0.5 는 이 노트북의 질의 세 개로 맞춘 값입니다. 다른 질의에도 맞는다는 보장은 없습니다.
- **근거 검증에는 차이 기준이 없습니다**: 가장 큰 probability 의 라벨을 고를 뿐이라, `supports` 가 낮은 probability 로도 1등이 될 수 있습니다.
- **예시 칩 문장**: 화면 탭의 예시 칩은 서버의 `SAMPLE_QUERIES` 를 베낀 것이고, 기준은 서버 목록입니다."""

RAG_NOTEBOOK: list[tuple[str, str]] = [
    (
        "md",
        """# 12. 문서 RAG: Jev 가 찾을 곳을 고르고, grep 이 찾고, LLM 이 쓴다

## 배경

문서에서 답을 찾는 RAG 는 보통 문서를 잘게 쪼개 임베딩으로 바꾸고, 질문과 가까운 조각을 가져옵니다. 이 방식은 벡터 저장소와 임베딩 모델이 필요하고, 왜 그 조각이 뽑혔는지 설명하기 어렵습니다.

이 노트북은 다른 방식을 씁니다. 사람이 문서 서랍을 뒤지는 순서를 그대로 따릅니다. 폴더를 고르고, 그 안에서 파일을 고르고, 파일 안에서 낱말로 문단을 찾습니다. 이 가운데 "어디를 볼지"와 "찾은 것으로 답해도 되는지"는 판단이라서 Jev 가 맡고, 문장을 쓰는 일만 LLM 이 맡습니다.

| 역할 | 맡는 쪽 | 하는 일 |
|---|---|---|
| 어디서 찾을지 | Jev (Choice) | 폴더 하나 이상, 파일 하나 이상을 고른다. 맞는 곳이 없으면 `none` 을 고른다. |
| 찾기 | grep (코드) | 선택된 파일에서 질의 낱말이 든 문단을 경로와 줄 번호와 함께 가져온다. |
| 답해도 되는지 | Jev (Noul) | 찾은 구절만으로 질의에 답할 수 있는지 예/아니오로 판단한다. |
| 쓰기 | LLM | 구절만 근거로 2~4문장으로 답한다. |
| 답이 구절에 근거하는지 | Jev (Choice) | 답이 구절과 맞는지, 어긋나는지, 구절에 없는 말인지 판단한다. |

용어를 먼저 정리합니다.

- **Choice**: 여러 option 중 하나를 고르는 질문입니다. Jev 는 option 마다 probability 를 돌려줍니다.
- **Noul**: 예/아니오 질문입니다. "예"일 probability 하나를 돌려줍니다.
- **probability**: 0 에서 1 사이의 숫자로, 그 option 이 맞다고 보는 정도입니다. 이 노트북의 판정은 모두 probability 를 기준값과 비교해서 합니다.
- **confidence**: probability 분포를 숫자 하나로 요약한 값입니다. Choice 와 Score 의 응답에 있고 Noul 에는 없습니다. 03번 노트북에서 캐스케이드에 썼습니다. 이 노트북은 1등 하나가 아니라 기준값 이상인 option 을 여러 개 골라야 하고 Noul 도 함께 쓰므로, confidence 를 거치지 않고 probability 에 기준값을 바로 겁니다.
- **Score**: 순서가 있는 척도 위의 위치를 묻는 질문입니다. 이 그래프에서는 쓰지 않습니다.

## 직관

도서관 사서를 떠올리면 됩니다. 사서는 먼저 서가(폴더)를 고르고, 그 서가에서 책(파일)을 고르고, 책을 펴서 해당 쪽을 찾습니다. 찾은 쪽으로 답할 수 있는지 한 번 더 따져 보고, 답을 쓴 뒤에는 쓴 내용이 그 쪽에 정말 있는지 확인합니다.

```
질의 ─▶ 폴더 선택 ─▶ 파일 선택 ─▶ 구절 검색 ─▶ 충분성 ─▶ 답변 ─▶ 근거 검증
        (Jev)        (Jev)        (grep)       (Jev)     (LLM)    (Jev)
          │            │            │            │          │
        none         none        구절 없음     아니오     거절 문장
          └────────────┴────────────┴────────────┴──────────┴─▶ 거기서 멈춤
```

Jev 호출은 질의 하나에 최대 4번입니다. 어느 단계에서든 멈출 사유가 생기면 그 자리에서 끝나고, 멈춘 이유가 `status` 로 남습니다.

## 이 노트북에서 확인하는 것

1. 폴더 선택과 파일 선택에서 probability 가 어떻게 나오는가
2. 기준값을 바꾸면 선택이 어떻게 달라지는가
3. 구절은 잡히지만 답은 없는 질의에서 어디서 멈추는가
4. 같은 질의를 세 번씩 돌렸을 때 결과가 얼마나 흔들리는가""",
    ),
    ("code", RAG_SETUP),
    (
        "md",
        """## 문서 구조

검색 대상은 `jev_agent/rag/documents/` 아래의 '테디마켓' 운영 안내 문서입니다. 색인은 폴더마다 있는 `_folder.md` 한 줄 설명과, 각 문서의 제목과 첫 문단(요약)만으로 만들어집니다. 본문은 검색할 때 읽습니다. Jev 는 이 설명과 요약만 보고 어디를 볼지 고릅니다.""",
    ),
    (
        "code",
        """print(f"폴더 {len(index['folders'])}개, 파일 {len(index['files'])}개")
print(pd.DataFrame(index["folders"]).rename(columns={"name": "폴더", "description": "설명"}).to_string(index=False))
files_table = pd.DataFrame(index["files"])[["folder", "key", "title", "summary"]]
files_table.columns = ["폴더", "파일 키", "제목", "요약"]
files_table.set_index("폴더")""",
    ),
    (
        "md",
        """## 폴더 선택

질의마다 Choice 질문 하나를 만듭니다. option 은 폴더 이름과 설명이고, 맨 뒤에 "해당 없음"을 뜻하는 `none` 을 붙입니다. 맞는 폴더가 없을 때 억지로 하나를 고르지 않게 하려는 장치입니다. option 은 이름순으로 넣고 `none` 을 마지막에 둡니다. 앞쪽 option 이 유리해지는 편향을 줄이기 위해서입니다.

골든 셋 `SAMPLE_QUERIES` 는 세 질의입니다.

| 라벨 | 질의 | 기대 |
|---|---|---|
| 정상 | 배송비는 얼마인가요? | 답을 낸다 |
| 두 폴더에 걸침 | 환불하면 사용한 적립금은 어떻게 되나요? | 답을 낸다. returns 와 membership 을 함께 봐야 한다 |
| 문서에 없음 | 주차장 약도를 팩스로 보내주세요 | 어디선가 멈춘다 |

아래 표는 질의마다 Jev 를 한 번 호출해서 받은 폴더별 probability 입니다.""",
    ),
    (
        "code",
        """folder_probabilities = {}
folder_rows = []
for sample in SAMPLE_QUERIES:
    state, questions = build_folder_question(index, sample["query"])
    result = jev.decide(state, questions)
    offered = list(questions["folder"]["criteria"])
    probabilities = read_probabilities(read_answer(result, "folder"), offered)
    folder_probabilities[sample["query"]] = probabilities
    folder_rows.append({"질의": sample["query"], **{key: round(value, 3) for key, value in probabilities.items()}})

print("usage.cost 의 Python 타입:", type(result.usage.get("cost")).__name__)
print("마지막 호출의 지연:", round(result.latency_ms), "ms")
pd.DataFrame(folder_rows).set_index("질의")""",
    ),
    (
        "md",
        """## 파일 선택과 grep

폴더 선택에서 기준값(`FOLDER_THRESHOLD`) 이상인 폴더를 최대 `MAX_FOLDERS` 개까지 고릅니다. 1등이 `none` 이면 아무것도 고르지 않고 거기서 멈춥니다. 고른 폴더 안의 파일들로 다시 Choice 질문을 만들어 파일을 고르고(`FILE_THRESHOLD` 이상, 최대 `MAX_FILES` 개), 고른 파일에서 grep 으로 구절을 찾습니다.

grep 은 질의를 낱말로 쪼개 조사를 하나 떼고, 그 낱말이 부분 문자열로 들어 있는 문단을 가져옵니다. 결과는 Jev 가 파일에 준 probability 순서를 따르고, 문단마다 `경로:줄 번호` 가 붙습니다.""",
    ),
    (
        "code",
        """path_by_key = {entry["key"]: entry["path"] for entry in index["files"]}
file_probabilities = {}

for sample in SAMPLE_QUERIES:
    query = sample["query"]
    folders = select_labels(folder_probabilities[query], FOLDER_THRESHOLD, MAX_FOLDERS)
    print(f"[{sample['label']}] {query}")
    print("  고른 폴더:", folders or "없음 (여기서 멈춤)")
    if not folders:
        continue
    state, questions = build_file_question(index, folders, query)
    result = jev.decide(state, questions)
    offered = list(questions["file"]["criteria"])
    probabilities = read_probabilities(read_answer(result, "file"), offered)
    file_probabilities[query] = probabilities
    keys = select_labels(probabilities, FILE_THRESHOLD, MAX_FILES)
    print("  파일 probability:", {key: round(value, 3) for key, value in probabilities.items()})
    print("  고른 파일:", keys or "없음 (여기서 멈춤)")
    if not keys:
        continue
    passages = search_passages(index, [path_by_key[key] for key in keys], query)
    print(f"  찾은 구절 {len(passages)}개")
    for passage in passages:
        print(f"    {passage['path']}:{passage['line']}  {passage['text'][:50]}")""",
    ),
    (
        "md",
        """## 기준값 실험

같은 probability 에 기준값만 바꿔서 적용해 봅니다. Jev 를 다시 부르지 않고 위에서 받은 값을 그대로 씁니다. 기준값이 낮으면 더 많은 폴더와 파일이 선택되고, 높으면 적게 선택됩니다. 1등이 `none` 이면 기준값과 상관없이 아무것도 선택하지 않는다는 점도 확인할 수 있습니다.""",
    ),
    (
        "code",
        """def threshold_table(probabilities_by_query, thresholds, limit):
    rows = []
    for query, probabilities in probabilities_by_query.items():
        row = {"질의": query}
        for threshold in thresholds:
            picked = select_labels(probabilities, threshold, limit)
            row[f"기준값 {threshold}"] = ", ".join(picked) or "(없음)"
        rows.append(row)
    return pd.DataFrame(rows).set_index("질의")

print(f"폴더 선택 (최대 {MAX_FOLDERS}개, 시작값 {FOLDER_THRESHOLD})")
threshold_table(folder_probabilities, [0.1, 0.25, 0.4], MAX_FOLDERS)""",
    ),
    (
        "code",
        """print(f"파일 선택 (최대 {MAX_FILES}개, 시작값 {FILE_THRESHOLD})")
threshold_table(file_probabilities, [0.1, 0.2, 0.4], MAX_FILES)""",
    ),
    (
        "md",
        """## 충분성으로 멈추는 사례

구절을 찾았다고 답할 수 있는 것은 아닙니다. "해외 배송비는 얼마인가요?" 는 배송비 문서의 문단과 낱말이 겹치지만, 문서에 해외 배송비는 적혀 있지 않습니다. 이런 질의를 grep 은 걸러내지 못합니다. 낱말이 겹치기 때문입니다.

그래서 구절을 찾은 뒤 Noul 질문 하나로 "이 구절만 읽고 질의에 답할 수 있는가" 를 묻습니다. "예"일 probability 가 기준값(`SUFFICIENCY_THRESHOLD`) 미만이면 LLM 을 부르지 않고 `insufficient` 로 끝납니다.

방어선은 하나 더 있습니다. 충분성을 통과했는데 구절에 답이 없으면, 답변 프롬프트가 LLM 에게 정해진 거절 문장만 쓰게 합니다. 그 문장이 오면 그래프는 같은 `insufficient` 로 끝냅니다. 두 경우는 `status` 가 같아서, 충분성 단계의 `verdict` 로 구분합니다.

- 충분성 단계의 verdict 가 `insufficient`: 충분성 probability 가 기준값 미만이라 첫째 방어선에서 멈췄습니다.
- 충분성 단계의 verdict 가 `sufficient` 인데 `status` 가 `insufficient`: 충분성은 통과했지만 LLM 이 거절 문장으로 답해서 둘째 방어선에서 멈췄습니다.

단계 표를 읽는 법을 하나 적어 둡니다. 충분성 단계에는 option 이 `sufficient` 하나뿐이고, 그 probability 가 곧 "예"일 probability 입니다. 그래서 "가장 큰 옵션" 칸에는 항상 `sufficient` 가 나오고, 답할 수 있는지는 "그 probability" 가 기준값 이상인지로 판정합니다.

실제로 실행한 결과를 그대로 적습니다. 질의는 바꾸지 않았습니다.""",
    ),
    (
        "code",
        STEPS_TABLE
        + """

graph = build_doc_rag_graph(jev=jev, llm=llm)
final_state = await graph.ainvoke({"payload": {"query": INSUFFICIENT_QUERY}})

print("질의:", INSUFFICIENT_QUERY)
if final_state.get("error"):
    print("오류:", final_state["error"])
else:
    output = final_state["output"]
    sufficiency = next((step for step in output["steps"] if step["kind"] == "sufficiency"), None)
    print("status:", output["status"])
    if sufficiency is not None:
        probability = sufficiency["probabilities"]["sufficient"]
        print(f"충분성 probability: {probability:.3f} (기준값 {SUFFICIENCY_THRESHOLD})")
        print("충분성 단계 verdict:", sufficiency["verdict"])
    print(steps_table(output).to_string(index=False))""",
    ),
    (
        "md",
        """## 전체 그래프를 세 번씩 돌리기

이제 `SAMPLE_QUERIES` 세 질의를 각각 세 번, 모두 9번 그래프로 실행합니다. 같은 입력을 보내도 Jev 의 probability 가 조금씩 달라지는지, 달라진다면 최종 결과(status, 선택된 폴더)가 바뀌는지 확인하려는 것입니다.

아래 표는 실행마다 한 줄입니다. 오류로 끝난 실행은 status 칸에 `error` 와 메시지가 나옵니다.""",
    ),
    (
        "code",
        """RUNS_PER_QUERY = 3
runs = []
for sample in SAMPLE_QUERIES:
    for run_number in range(1, RUNS_PER_QUERY + 1):
        state = await graph.ainvoke({"payload": {"query": sample["query"]}})
        output = state.get("output")
        if output is None:
            runs.append({"label": sample["label"], "run": run_number, "status": f"error: {state.get('error')}",
                         "folders": [], "answer": None, "grounding": None, "steps": []})
            continue
        runs.append({"label": sample["label"], "run": run_number, "status": output["status"],
                     "folders": output["folders"], "answer": output["answer"],
                     "grounding": output["grounding"], "steps": output["steps"]})


def step_probabilities(run, kind):
    step = next((step for step in run["steps"] if step["kind"] == kind), None)
    return step["probabilities"] if step else {}


run_rows = []
for run in runs:
    folder_probs = step_probabilities(run, "folder")
    sufficiency = step_probabilities(run, "sufficiency").get("sufficient")
    run_rows.append({
        "질의": run["label"],
        "회차": run["run"],
        "status": run["status"],
        "폴더": ", ".join(run["folders"]) or "(없음)",
        "returns": round(folder_probs["returns"], 3) if "returns" in folder_probs else None,
        "membership": round(folder_probs["membership"], 3) if "membership" in folder_probs else None,
        "충분성": round(sufficiency, 3) if sufficiency is not None else None,
        "근거 검증": run["grounding"],
    })
pd.DataFrame(run_rows)""",
    ),
    (
        "md",
        """### 질의별 최솟값과 최댓값

위 표에서 질의마다 세 번의 probability 중 가장 작은 값과 가장 큰 값을 나란히 놓습니다. 비어 있는 칸은 그 단계까지 가지 못했다는 뜻입니다.""",
    ),
    (
        "code",
        """def min_max(values):
    values = [value for value in values if value is not None]
    return f"{min(values):.3f} ~ {max(values):.3f}" if values else "-"


spread_rows = []
for sample in SAMPLE_QUERIES:
    mine = [run for run in runs if run["label"] == sample["label"]]
    spread_rows.append({
        "질의": sample["label"],
        "returns": min_max([step_probabilities(run, "folder").get("returns") for run in mine]),
        "membership": min_max([step_probabilities(run, "folder").get("membership") for run in mine]),
        "shipping": min_max([step_probabilities(run, "folder").get("shipping") for run in mine]),
        "none": min_max([step_probabilities(run, "folder").get("none") for run in mine]),
        "충분성": min_max([step_probabilities(run, "sufficiency").get("sufficient") for run in mine]),
    })
pd.DataFrame(spread_rows).set_index("질의")""",
    ),
    (
        "md",
        """### 기대값과 비교

골든 셋의 기대값을 실행 결과와 맞춰 봅니다. 기대값은 결과에 맞춰 고치지 않았습니다.

- 기대가 `answered` 인 질의는 세 번 모두 `status` 가 `answered` 여야 합니다.
- "두 폴더에 걸침" 질의는 세 번 모두 고른 폴더에 `returns` 와 `membership` 이 함께 있어야 합니다.
- 기대가 `stopped` 인 질의는 세 번 모두 종료 사유 네 가지(`no_folder`, `no_file`, `no_passage`, `insufficient`) 중 하나로 끝나고 답이 없어야 합니다. 어느 단계에서 멈췄는지는 따지지 않습니다.""",
    ),
    (
        "code",
        """STOP_STATUSES = {"no_folder", "no_file", "no_passage", "insufficient"}
gate_rows = []
for sample in SAMPLE_QUERIES:
    mine = [run for run in runs if run["label"] == sample["label"]]
    if sample["expected"] == "answered":
        passed = all(run["status"] == "answered" for run in mine)
    else:
        passed = all(run["status"] in STOP_STATUSES and run["answer"] is None for run in mine)
    if sample["label"] == "두 폴더에 걸침":
        passed = passed and all({"returns", "membership"} <= set(run["folders"]) for run in mine)
    gate_rows.append({
        "질의": sample["label"],
        "기대": sample["expected"],
        "세 번의 status": ", ".join(run["status"] for run in mine),
        "통과": passed,
    })
pd.DataFrame(gate_rows).set_index("질의")""",
    ),
    (
        "md",
        """### 마지막 실행의 단계별 판정과 답변

질의마다 세 번째 실행의 단계를 표로 보고, 답변과 근거 검증 결과를 함께 봅니다.""",
    ),
    (
        "code",
        """for sample in SAMPLE_QUERIES:
    last = [run for run in runs if run["label"] == sample["label"]][-1]
    print(f"[{sample['label']}] {sample['query']}")
    print("  status:", last["status"], "/ 근거 검증:", last["grounding"])
    print("  답변:", last["answer"])
    if last["steps"]:
        print(steps_table({"steps": last["steps"]}).to_string(index=False))
    print()""",
    ),
    (
        "md",
        """### 호출 횟수와 비용

9번 실행에서 Jev 를 몇 번 불렀고 비용이 얼마였는지 합산합니다. 비용은 Jev 응답의 `usage.cost` 를 단계마다 더한 값이고, 답변을 쓰는 LLM 의 비용은 들어 있지 않습니다.""",
    ),
    (
        "code",
        """all_steps = [step for run in runs for step in run["steps"]]
llm_calls = sum(1 for run in runs if run["answer"] is not None)
latencies = [step["latency_ms"] for step in all_steps]
print(f"Jev 호출 {len(all_steps)}회, 비용 합계 ${sum(step['cost'] for step in all_steps):.6f}")
print(f"Jev 지연: 중앙값 {statistics.median(latencies)}ms, 최솟값 {min(latencies)}ms, 최댓값 {max(latencies)}ms")
print(f"답변을 쓴 LLM 호출: {llm_calls}회")""",
    ),
    ("md", RAG_LIMITS),
    ("md", RAG_RESULTS_SUMMARY),
]
