"""
Smart Farm 숙성도 분류기(MobileNetV3-small) 정확도 재현 평가.

배경: 원본 step2_train.py 는 cropped_dataset 970장 '전체'로 학습 → 저장 모델의
'학습 정확도'만 알 수 있어 과대평가됨. 신뢰 가능한 수치를 위해 동일 설정으로
80/20 '층화분할' 후 20% 홀드아웃에서 평가한다(= 재현 평가, 그때 그 모델과는 다른 인스턴스).

원본 하이퍼파라미터 그대로: MobileNetV3-small(pretrained) + Adam(lr=0.001) + 10 epochs + batch16.
원본은 안 건드림. 데이터만 읽음.
"""
import os, sys, json, random
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from torchvision.models import mobilenet_v3_small
try:
    from torchvision.models import MobileNet_V3_Small_Weights
    _WEIGHTS = MobileNet_V3_Small_Weights.IMAGENET1K_V1
except Exception:
    _WEIGHTS = None
from torch.utils.data import DataLoader, Subset

# --- 경로 ---
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(
    HERE, "..", "..", "tomato_robot", "cropped_dataset"))
RESULTS_DIR = os.path.join(HERE, "results")

# --- 설정 (원본 step2_train.py 와 동일) ---
BATCH_SIZE = 16
LEARNING_RATE = 0.001
EPOCHS = 10
VAL_RATIO = 0.2
SEED = 42
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def stratified_split(dataset, val_ratio, seed):
    """클래스별로 동일 비율 분할(층화). 클래스 불균형(ripe476/semi139/unripe355) 대응."""
    by_class = {}
    for idx, (_, label) in enumerate(dataset.samples):
        by_class.setdefault(label, []).append(idx)
    rng = random.Random(seed)
    train_idx, val_idx = [], []
    for label, idxs in by_class.items():
        idxs = idxs[:]
        rng.shuffle(idxs)
        n_val = max(1, int(len(idxs) * val_ratio))
        val_idx += idxs[:n_val]
        train_idx += idxs[n_val:]
    return train_idx, val_idx


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    torch.manual_seed(SEED)
    random.seed(SEED)

    if not os.path.isdir(DATA_DIR):
        print(f"[오류] 데이터 폴더 없음: {DATA_DIR}")
        sys.exit(1)

    tfm = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    full = datasets.ImageFolder(DATA_DIR, transform=tfm)
    classes = full.classes  # ['ripe','semi_ripe','unripe']
    print(f"클래스: {classes} / 전체 {len(full)}장 / device={DEVICE}")

    train_idx, val_idx = stratified_split(full, VAL_RATIO, SEED)
    print(f"학습 {len(train_idx)}장 / 검증(홀드아웃) {len(val_idx)}장")
    train_loader = DataLoader(Subset(full, train_idx), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(Subset(full, val_idx), batch_size=BATCH_SIZE, shuffle=False)

    model = mobilenet_v3_small(weights=_WEIGHTS)
    in_f = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_f, len(classes))
    model = model.to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

    for epoch in range(EPOCHS):
        model.train()
        run_loss, correct, total = 0.0, 0, 0
        for x, y in train_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            run_loss += loss.item()
            _, pred = torch.max(out, 1)
            total += y.size(0)
            correct += (pred == y).sum().item()
        print(f"Epoch {epoch+1}/{EPOCHS} loss={run_loss/len(train_loader):.4f} train_acc={100*correct/total:.2f}%")

    # --- 홀드아웃 평가 ---
    model.eval()
    n = len(classes)
    conf = [[0]*n for _ in range(n)]
    correct, total = 0, 0
    with torch.no_grad():
        for x, y in val_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            _, pred = torch.max(model(x), 1)
            for t, p in zip(y.tolist(), pred.tolist()):
                conf[t][p] += 1
                total += 1
                correct += int(t == p)

    overall = 100*correct/total
    print(f"\n=== 홀드아웃({len(val_idx)}장) 정확도: {overall:.2f}% ===")
    per_class = {}
    for i, c in enumerate(classes):
        tp = conf[i][i]
        support = sum(conf[i])
        col = sum(conf[r][i] for r in range(n))
        recall = tp/support if support else 0
        precision = tp/col if col else 0
        f1 = 2*precision*recall/(precision+recall) if (precision+recall) else 0
        per_class[c] = {"precision": round(precision, 4), "recall": round(recall, 4),
                        "f1": round(f1, 4), "support": support}
        print(f"  {c:10s} P={precision:.3f} R={recall:.3f} F1={f1:.3f} (n={support})")
    print("혼동행렬(행=실제, 열=예측):", classes)
    for i, c in enumerate(classes):
        print(f"  {c:10s} {conf[i]}")

    out = {"overall_accuracy_pct": round(overall, 2), "n_val": len(val_idx),
           "n_train": len(train_idx), "classes": classes, "per_class": per_class,
           "confusion_matrix": conf, "epochs": EPOCHS, "seed": SEED,
           "note": "재현 평가(80/20 층화분할 홀드아웃). 원본 저장모델과는 다른 인스턴스."}
    with open(os.path.join(RESULTS_DIR, "accuracy.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {os.path.join(RESULTS_DIR, 'accuracy.json')}")


if __name__ == "__main__":
    main()
