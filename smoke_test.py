import sys

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> int:
    failures = 0

    with httpx.Client(base_url=BASE, timeout=900.0) as c:
        health = c.get("/health").json()
        print("health:", health["status"], health["config"])
        print("models:", c.get("/models").json()["allowed"])
        print("qtypes:", c.get("/qtypes").json()["types"])

        index = c.get("/")
        print("index ->", index.status_code, len(index.content), "bytes")
        failures += index.status_code != 200

        bad = c.post("/predict", json={"state": "hi", "questions": {}})
        print("empty questions ->", bad.status_code)
        failures += bad.status_code != 422

        bad = c.post(
            "/predict", json={"state": "hi", "questions": {"a": {"type": "choice", "instructions": "x"}}}
        )
        print("choice without criteria ->", bad.status_code)
        failures += bad.status_code != 422

        bad = c.post(
            "/predict", json={"state": "hi", "questions": {"a": {"type": "wat", "instructions": "x"}}}
        )
        print("unknown qtype ->", bad.status_code)
        failures += bad.status_code != 422

        bad = c.post(
            "/predict",
            json={"state": "x" * 60_000, "questions": {"a": {"type": "noul", "instructions": "x?"}}},
        )
        print("oversized state ->", bad.status_code)
        failures += bad.status_code != 413

        preset_data = c.get("/presets").json()
        print("groups:", preset_data["groups"])
        for key, preset in preset_data["presets"].items():
            if key == "custom":
                continue
            body = {"state": preset["state"], "questions": preset["questions"]}
            r = c.post("/predict", json=body)
            print(f"\n=== {key} -> {r.status_code}")
            if r.status_code != 200:
                print(r.text[:500])
                failures += 1
                continue
            data = r.json()
            for name, ans in data.get("answers", {}).items():
                verdict = ans.get("choice", ans.get("score", ans.get("noul")))
                conf = ans.get("answer_confidence")
                print(f"  {name:18s} {ans.get('type'):7s} -> {verdict!r}  conf={conf}")
            print("  routing:", data.get("routing", {}).get("model"), "|", data.get("routing", {}).get("reason", "")[:90])
            print("  elapsed_ms:", data.get("elapsed_ms"), "usage:", data.get("usage"))

        preset = preset_data["presets"]["triage"]
        batch = c.post(
            "/predict/batch",
            json={
                "states": [
                    "Server is down, customers cannot check out.",
                    "Bonjour, je voudrais annuler mon abonnement.",
                    "Hi, we were billed twice for March. Please refund the duplicate today.",
                ],
                "questions": preset["questions"],
            },
        )
        print("\n=== batch ->", batch.status_code)
        if batch.status_code == 200:
            data = batch.json()
            print("  count:", data["count"], "elapsed_ms:", data["elapsed_ms"])
            if data["count"] != 3:
                print("  FAIL count", data["count"], "!= 3")
                failures += 1
            # Read the question ids off the preset instead of hardcoding them. The triage
            # preset has no `department` question, so a hardcoded lookup silently printed None
            # for every state and the batch block asserted nothing.
            qids = [q for q in preset["questions"]]
            for item in data["results"]:
                if "error" in item:
                    print("  error:", item["error"][:120])
                    failures += 1
                    continue
                ans = item.get("answers", {})
                missing = [q for q in qids if q not in ans]
                if missing:
                    print("  FAIL answers missing", missing)
                    failures += 1
                intent = ans.get("intent", {}).get("choice")
                urgent = ans.get("is_urgent", {}).get("noul")
                refund = ans.get("refund_requested", {}).get("noul")
                model = item.get("routing", {}).get("model")
                print(f"  {model:14s} intent={intent!r:10s} is_urgent={urgent} "
                      f"refund_requested={refund}")
        else:
            print(batch.text[:500])
            failures += 1

        print("\nmissing route ->", c.get("/nope").status_code)

    print("\nFAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
