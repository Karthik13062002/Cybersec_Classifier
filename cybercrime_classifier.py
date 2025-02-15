# -*- coding: utf-8 -*-
"""cybercrime_classifier.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1_Nzu_CXnT8xxtFIXU0QflmrP-KE2Cefr
"""

# Cell 1: Install necessary packages
!pip install transformers datasets evaluate nltk

# Cell 2: Import libraries
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
import torch
from torch.utils.data import Dataset, DataLoader
from torch.cuda.amp import autocast, GradScaler

nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('wordnet', quiet=True)

# Set device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Cell 3: Load data
from google.colab import drive
drive.mount('/content/drive')
train_data = pd.read_csv('/content/drive/MyDrive/cybercrime_classifier/train.csv')
test_data = pd.read_csv('/content/drive/MyDrive/cybercrime_classifier/test.csv')

# Cell 4: Define the Text Preprocessor and Dataset classes
class TextPreprocessor:
    def __init__(self):
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))

    def preprocess(self, text):
        if pd.isna(text):
            return ""
        text = re.sub(r'[^a-zA-Z\s]', ' ', str(text).lower())
        tokens = word_tokenize(text)
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens if token not in self.stop_words]
        return ' '.join(tokens)

class CybercrimeDataset(Dataset):
    def __init__(self, texts, category_labels=None, subcategory_labels=None, tokenizer=None, max_length=256):
        self.texts = texts
        self.category_labels = category_labels
        self.subcategory_labels = subcategory_labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        encoding = self.tokenizer(self.texts[idx], truncation=True, padding='max_length', max_length=self.max_length, return_tensors='pt')
        item = {'input_ids': encoding['input_ids'].flatten(), 'attention_mask': encoding['attention_mask'].flatten()}
        if self.category_labels is not None:
            item['category_labels'] = torch.tensor(self.category_labels[idx])
        if self.subcategory_labels is not None:
            item['subcategory_labels'] = torch.tensor(self.subcategory_labels[idx])
        return item

# Cell 5: Data Preparation
preprocessor = TextPreprocessor()
train_data['processed_text'] = train_data['crimeaditionalinfo'].apply(preprocessor.preprocess)
test_data['processed_text'] = test_data['crimeaditionalinfo'].apply(preprocessor.preprocess)

# Encoding labels
category_encoder = LabelEncoder()
subcategory_encoder = LabelEncoder()
train_data['category_encoded'] = category_encoder.fit_transform(train_data['category'])
train_data['subcategory_encoded'] = subcategory_encoder.fit_transform(train_data['sub_category'])

# Tokenizer
tokenizer = AutoTokenizer.from_pretrained('distilbert-base-uncased')

# Cell 6: Training Preparation
train_dataset = CybercrimeDataset(
    texts=train_data['processed_text'].values,
    category_labels=train_data['category_encoded'].values,
    subcategory_labels=train_data['subcategory_encoded'].values,
    tokenizer=tokenizer
)

train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

# Cell 7a: Train Category Model
def train_category_model():
    num_category_labels = len(category_encoder.classes_)
    model = AutoModelForSequenceClassification.from_pretrained(
        'distilbert-base-uncased', num_labels=num_category_labels
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=len(train_loader) * 3)
    scaler = torch.amp.GradScaler()

    for epoch in range(3):
        model.train()
        total_loss = 0
        for batch in train_loader:
            optimizer.zero_grad()
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            category_labels = batch['category_labels'].to(device)

            with torch.amp.autocast(device_type='cuda'):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=category_labels)
                loss = outputs.loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            total_loss += loss.item()

        print(f"Epoch {epoch + 1}: Loss = {total_loss / len(train_loader)}")

    model.save_pretrained('category_classifier')
    print("Category model training completed and saved.")

train_category_model()

# Cell 7b: Train Subcategory Model
def train_subcategory_model():
    num_subcategory_labels = len(subcategory_encoder.classes_)
    model = AutoModelForSequenceClassification.from_pretrained(
        'distilbert-base-uncased', num_labels=num_subcategory_labels
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=len(train_loader) * 3)
    scaler = torch.amp.GradScaler()

    for epoch in range(3):
        model.train()
        total_loss = 0
        for batch in train_loader:
            optimizer.zero_grad()
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            subcategory_labels = batch['subcategory_labels'].to(device)

            with torch.amp.autocast(device_type='cuda'):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=subcategory_labels)
                loss = outputs.loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            total_loss += loss.item()

        print(f"Epoch {epoch + 1}: Loss = {total_loss / len(train_loader)}")

    model.save_pretrained('subcategory_classifier')
    print("Subcategory model training completed and saved.")

train_subcategory_model()

# Cell 8: Load Model for Prediction
category_model = AutoModelForSequenceClassification.from_pretrained('category_classifier').to(device)
subcategory_model = AutoModelForSequenceClassification.from_pretrained('subcategory_classifier').to(device)

category_model.eval()
subcategory_model.eval()

# Cell 9: Prediction Setup
test_dataset = CybercrimeDataset(texts=test_data['processed_text'].values, tokenizer=tokenizer)
test_loader = DataLoader(test_dataset, batch_size=256, shuffle=False)

# Cell 10: Making Predictions

def make_predictions():
    category_predictions, subcategory_predictions = [], []

    with torch.no_grad():
        for batch in test_loader:
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)

            # Predict categories
            category_outputs = category_model(input_ids=input_ids, attention_mask=attention_mask)
            category_preds = category_outputs.logits.argmax(dim=-1).cpu().numpy()
            category_predictions.extend(category_preds)

            # Predict subcategories
            subcategory_outputs = subcategory_model(input_ids=input_ids, attention_mask=attention_mask)
            subcategory_preds = subcategory_outputs.logits.argmax(dim=-1).cpu().numpy()
            subcategory_predictions.extend(subcategory_preds)

    predicted_categories = category_encoder.inverse_transform(category_predictions)
    predicted_subcategories = subcategory_encoder.inverse_transform(subcategory_predictions)

    test_data['predicted_category'] = predicted_categories
    test_data['predicted_subcategory'] = predicted_subcategories
    test_data.to_csv('/content/drive/MyDrive/cybercrime_classifier/predictions_output.csv', index=False)
    print("Predictions saved to 'predictions_output.csv'")

make_predictions()

"""Metrics"""

# Cell 11: Calculating Metrics

from sklearn.metrics import confusion_matrix
from sklearn import metrics
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('/content/drive/MyDrive/cybercrime_classifier/predictions_output.csv')

conf_matrix = metrics.confusion_matrix(df['category'], df['predicted_category'])

categories = ['Online and Social Media Related Crime', 'Online Financial Fraud',
       'Online Gambling  Betting',
       'RapeGang Rape RGRSexually Abusive Content',
       'Any Other Cyber Crime', 'Cyber Attack/ Dependent Crimes',
       'Cryptocurrency Crime', 'Sexually Explicit Act',
       'Sexually Obscene material',
       'Hacking  Damage to computercomputer system etc',
       'Cyber Terrorism',
       'Child Pornography CPChild Sexual Abuse Material CSAM',
       'Online Cyber Trafficking', 'Ransomware',
       'Report Unlawful Content']
sns.heatmap(conf_matrix,
            annot=True,cmap='YlOrRd',
            xticklabels=categories, cbar=False)

plt.yticks(np.arange(15),categories)
plt.ylabel('True labels');
plt.xlabel('Predicted labels');
plt.title('Confusion matrix');

print(metrics.classification_report(df['category'], df['predicted_category'], digits=3))

print(metrics.classification_report(df['sub_category'].astype(str), df['predicted_subcategory'].astype(str), digits=3))