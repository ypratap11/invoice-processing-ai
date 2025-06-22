"""
ML Classification for document types using scikit-learn
"""
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from typing import List, Tuple, Dict
import logging
import os

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """ML classifier for document types (Invoice, Receipt, Purchase Order)"""

    def __init__(self, model_path: str = None):
        self.pipeline = None
        self.classes = ["invoice", "receipt", "purchase_order"]

        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        else:
            self._create_pipeline()

    def _create_pipeline(self):
        """Create ML pipeline with TF-IDF and Random Forest"""
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                max_features=1000,
                stop_words='english',
                ngram_range=(1, 2),
                lowercase=True
            )),
            ('classifier', RandomForestClassifier(
                n_estimators=100,
                random_state=42,
                class_weight='balanced'
            ))
        ])

    def train_with_sample_data(self) -> Dict:
        """Train with sample data for demo purposes"""
        # Sample training data
        texts = [
            # Invoice samples
            "Invoice number 12345 total amount due $500.00 payment terms net 30 days",
            "Bill invoice #INV-001 subtotal $200 tax $20 total $220 due date 2024-01-15",
            "Invoice from ABC Company amount $750 please remit payment by due date",
            "Tax invoice total amount $1200 GST included due upon receipt",
            "Invoice #987 billing address total amount payable $450",

            # Receipt samples
            "Receipt thank you for your purchase total paid $25.50 cash transaction",
            "Store receipt purchase date today total $15.75 credit card payment",
            "Receipt #R001 items purchased total paid $85.00 change due $0.00",
            "Thank you receipt total amount $55 paid in full transaction complete",
            "Sales receipt customer copy total $125 payment method visa",

            # Purchase Order samples
            "Purchase order PO-789 quantity 10 unit price $15.00 delivery date next week",
            "PO number 456 ordered by John Smith deliver to warehouse total $500",
            "Purchase order #PO001 quantity 25 items unit cost $12 order total $300",
            "Order form PO-555 requested delivery shipping address order quantity 5",
            "Purchase order from supplier quantity ordered 50 units delivery terms"
        ]

        labels = (
                ["invoice"] * 5 +
                ["receipt"] * 5 +
                ["purchase_order"] * 5
        )

        return self.train(texts, labels)

    def train(self, texts: List[str], labels: List[str]) -> Dict:
        """
        Train the classification model

        Args:
            texts: List of document texts
            labels: List of corresponding labels

        Returns:
            Training metrics and results
        """
        try:
            print(f"🤖 Training document classifier with {len(texts)} samples...")

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42, stratify=labels
            )

            # Train model
            self.pipeline.fit(X_train, y_train)

            # Evaluate
            y_pred = self.pipeline.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            report = classification_report(y_test, y_pred, output_dict=True)

            print(f"✅ Model trained successfully!")
            print(f"   - Accuracy: {accuracy:.2%}")
            print(f"   - Training samples: {len(X_train)}")
            print(f"   - Test samples: {len(X_test)}")

            logger.info(f"Model trained with accuracy: {accuracy:.4f}")

            return {
                "accuracy": accuracy,
                "classification_report": report,
                "test_size": len(X_test),
                "train_size": len(X_train)
            }

        except Exception as e:
            logger.error(f"Training failed: {str(e)}")
            print(f"❌ Training failed: {str(e)}")
            raise

    def predict(self, text: str) -> str:
        """Predict document type for a single text"""
        if not self.pipeline:
            raise ValueError("Model not trained or loaded")

        prediction = self.pipeline.predict([text])[0]
        return prediction

    def predict_proba(self, text: str) -> Dict[str, float]:
        """Get prediction probabilities for all classes"""
        if not self.pipeline:
            raise ValueError("Model not trained or loaded")

        probabilities = self.pipeline.predict_proba([text])[0]
        return dict(zip(self.pipeline.classes_, probabilities))

    def batch_predict(self, texts: List[str]) -> List[Dict]:
        """Predict document types for multiple texts"""
        if not self.pipeline:
            raise ValueError("Model not trained or loaded")

        predictions = self.pipeline.predict(texts)
        probabilities = self.pipeline.predict_proba(texts)

        results = []
        for i, (pred, probs) in enumerate(zip(predictions, probabilities)):
            result = {
                "prediction": pred,
                "confidence": max(probs),
                "probabilities": dict(zip(self.pipeline.classes_, probs))
            }
            results.append(result)

        return results

    def save_model(self, path: str):
        """Save trained model to disk"""
        if not self.pipeline:
            raise ValueError("No model to save")

        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.pipeline, path)
        print(f"💾 Model saved to {path}")
        logger.info(f"Model saved to {path}")

    def load_model(self, path: str):
        """Load model from disk"""
        try:
            self.pipeline = joblib.load(path)
            print(f"📁 Model loaded from {path}")
            logger.info(f"Model loaded from {path}")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            print(f"❌ Failed to load model: {str(e)}")
            raise


# Test function
def test_classifier():
    """Test the classifier with sample data"""
    try:
        print("🧪 Testing Document Classifier...")

        classifier = DocumentClassifier()

        # Train with sample data
        training_results = classifier.train_with_sample_data()

        # Test predictions
        test_texts = [
            "Invoice #12345 Amount Due: $500.00 Due Date: 2024-01-15",
            "Receipt - Thank you for your purchase! Total Paid: $25.50",
            "Purchase Order #PO789 Quantity: 10 Unit Price: $15.00"
        ]

        print(f"\n🔍 Testing predictions:")
        for i, text in enumerate(test_texts, 1):
            prediction = classifier.predict(text)
            probabilities = classifier.predict_proba(text)

            print(f"\nTest {i}:")
            print(f"Text: {text}")
            print(f"Prediction: {prediction}")
            print(f"Confidence: {max(probabilities.values()):.2%}")

        # Save model
        classifier.save_model("data/models/document_classifier.pkl")

        print("✅ Classifier test successful!")
        return True

    except Exception as e:
        print(f"❌ Classifier test failed: {str(e)}")
        return False


if __name__ == "__main__":
    test_classifier()