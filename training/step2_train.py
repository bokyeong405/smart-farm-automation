import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader

# --- 설정 ---
DATA_DIR = 'cropped_dataset'   
MODEL_SAVE_PATH = 'classifier_model.pth'
NUM_CLASSES = 3                
BATCH_SIZE = 16 # 메모리 부족 시 줄이세요
LEARNING_RATE = 0.001
EPOCHS = 10
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def train_classifier():
    print(f"Training on device: {DEVICE}")
    
    data_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    try:
        dataset = datasets.ImageFolder(DATA_DIR, transform=data_transforms)
    except Exception as e:
        print(f"Error: 데이터 폴더 구조를 확인하세요. ({DATA_DIR})")
        return

    print(f"Classes: {dataset.classes}") 
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = models.mobilenet_v3_small(pretrained=True)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, NUM_CLASSES)
    model = model.to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

    model.train()
    for epoch in range(EPOCHS):
        running_loss = 0.0
        correct = 0
        total = 0
        for inputs, labels in dataloader:
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        print(f"Epoch [{epoch+1}/{EPOCHS}] Loss: {running_loss/len(dataloader):.4f} | Acc: {100*correct/total:.2f}%")

    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"Saved model to {MODEL_SAVE_PATH}")

if __name__ == "__main__":
    train_classifier()