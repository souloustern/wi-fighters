import pandas as pd
import numpy as np
from datetime import datetime
import re

def format_currency(amount):
    return f"{amount:,.0f}".replace(',', ' ').replace('.', ',')


def get_month_name(month_num):
    months = {
        1: 'январе', 2: 'феврале', 3: 'марте', 4: 'апреле',
        5: 'мае', 6: 'июне', 7: 'июле', 8: 'августе',
        9: 'сентябре', 10: 'октябре', 11: 'ноябре', 12: 'декабре'
    }
    return months.get(month_num, '')



class ClientAnalyzer:
    def __init__(self, transactions_df, transfers_df):
        self.transactions = transactions_df
        self.transfers = transfers_df
        self.client_code = transactions_df['client_code'].iloc[0]
        self.name = transactions_df['name'].iloc[0]
        self.status = transactions_df['status'].iloc[0]
        self.city = transactions_df['city'].iloc[0]

        if 'avg_monthly_balance_KZT' in transactions_df.columns:
            self.avg_balance = transactions_df['avg_monthly_balance_KZT'].iloc[0]
        else:
            salary_incomes = transfers_df[transfers_df['type'] == 'salary_in']['amount'].sum()
            self.avg_balance = salary_incomes / 3  # Примерная оценка

        self.analyze_data()

    def analyze_data(self):
        # Анализ транзакций
        self.spending_by_category = self.transactions.groupby('category')['amount'].sum()
        self.total_spending = self.transactions['amount'].sum()
        self.avg_transaction = self.transactions['amount'].mean()

        # Анализ частоты операций
        self.transactions['date'] = pd.to_datetime(self.transactions['date'])
        self.transactions['month'] = self.transactions['date'].dt.month
        self.monthly_spending = self.transactions.groupby('month')['amount'].sum()

        # Анализ переводов
        self.transfers['date'] = pd.to_datetime(self.transfers['date'])
        self.transfer_stats = self.transfers.groupby('type').agg(
            amount=('amount', 'sum'),
            count=('amount', 'count')
        ).reset_index()

        # Специфические признаки
        self.has_loan_payments = ('loan_payment_out' in self.transfers['type'].values)
        self.has_regular_salary = (self.transfers['type'] == 'salary_in').sum() >= 2
        self.cashback_received = self.transfers[self.transfers['type'] == 'cashback_in']['amount'].sum()
        self.atm_withdrawals = self.transfers[self.transfers['type'] == 'atm_withdrawal']['amount'].sum()

        # Месяц с максимальными тратами (для персонализации)
        self.top_spending_month = self.monthly_spending.idxmax() if not self.monthly_spending.empty else 6

    def calculate_product_scores(self):
        scores = {}

        # 1. Карта для путешествий
        travel_categories = ['Такси', 'Путешествия', 'Отели', 'АЗС']
        travel_spending = sum(self.spending_by_category.get(cat, 0) for cat in travel_categories)
        scores['Карта для путешествий'] = travel_spending * 0.04  # 4% кешбэк

        # 2. Премиальная карта
        premium_categories = ['Кафе и рестораны', 'Ювелирные украшения', 'Косметика и Парфюмерия']
        premium_spending = sum(self.spending_by_category.get(cat, 0) for cat in premium_categories)

        premium_score = 0
        if self.avg_balance > 6000000:
            premium_score += 4  # Максимальный кешбэк
        elif self.avg_balance > 1000000:
            premium_score += 3
        else:
            premium_score += 2

        premium_score += premium_spending * 0.04
        scores['Премиальная карта'] = premium_score

        # 3. Кредитная карта
        top_categories = self.spending_by_category.nlargest(3)
        credit_score = sum(top_categories) * 0.10  # До 10% кешбэк
        if self.has_loan_payments:
            credit_score *= 1.2  # Бонус для тех, у кого уже есть кредиты
        scores['Кредитная карта'] = credit_score

        # 4. Обмен валют (FX)
        fx_operations = len(self.transfers[self.transfers['type'].isin(['fx_buy', 'fx_sell'])])
        scores['Обмен валют'] = fx_operations * 10000  # Чем больше операций, тем выше score

        # 5. Кредит наличными
        loan_score = 0
        if self.has_loan_payments:
            loan_score += 50000
        if self.total_spending > 500000 and self.avg_balance < 300000:
            loan_score += 70000
        scores['Кредит наличными'] = loan_score

        # 6-8. Депозиты
        deposit_rate = 0.145  # Средняя ставка
        deposit_score = self.avg_balance * deposit_rate / 12  # Примерный месячный доход

        scores['Депозит Мультивалютный (KZT/USD/RUB/EUR)'] = deposit_score * 0.9
        scores['Депозит Сберегательный (защита KDIF)'] = deposit_score * 1.1  # Выше ставка
        scores['Депозит Накопительный'] = deposit_score

        # 9. Инвестиции
        investment_score = 0
        if self.avg_balance > 1000000:
            investment_score = 50000
        scores['Инвестиции'] = investment_score

        # 10. Золотые слитки
        gold_score = self.avg_balance * 0.05  # Для диверсификации
        scores['Золотые слитки'] = gold_score

        return scores

    def generate_push_notification(self, product):
        """Генерация персонализированного push-уведомления"""

        if product == 'Карта для путешествий':
            travel_spending = sum(self.spending_by_category.get(cat, 0) for cat in ['Такси', 'Путешествия', 'Отели'])
            cashback = travel_spending * 0.04
            month_name = get_month_name(self.top_spending_month)

            return f"{self.name}, в {month_name} у вас было много поездок. С тревел-картой вы могли бы вернуть до {format_currency(cashback)} ₸ кешбэка. Оформите карту в приложении."

        elif product == 'Премиальная карта':
            restaurant_spending = self.spending_by_category.get('Кафе и рестораны', 0)
            return f"{self.name}, у вас стабильный доход и траты в ресторанах. Премиальная карта даст до 4% кешбэка и бесплатные снятия. Подключите сейчас."

        elif product == 'Кредитная карта':
            top_cats = self.spending_by_category.nlargest(3)
            categories = ", ".join(top_cats.index.tolist())
            return f"{self.name}, ваши основные траты — {categories}. Кредитная карта даёт до 10% кешбэка в этих категориях. Оформите карту."

        elif product == 'Обмен валют':
            return f"{self.name}, в приложении доступен выгодный обмен валют без комиссии 24/7. Настроить автообмен по целевым курсам."

        elif product in ['Депозит Мультивалютный (KZT/USD/RUB/EUR)',
                         'Депозит Сберегательный (защита KDIF)',
                         'Депозит Накопительный']:
            return f"{self.name}, у вас есть свободные средства. Разместите их на вкладе под выгодный процент. Открыть вклад."

        elif product == 'Инвестиции':
            return f"{self.name}, попробуйте инвестиции с низким порогом входа и без комиссий в первый год. Открыть счёт."

        elif product == 'Кредит наличными':
            return f"{self.name}, если нужны средства на крупные цели — оформляйте кредит наличными с гибкими условиями. Узнать ставку."

        elif product == 'Золотые слитки':
            return f"{self.name},考虑 диверсификацию сбережений? Золотые слитки — надежный способ сохранения стоимости. Узнать больше."

        return "Персонализированное предложение для вас."



def process_client(transactions_path, transfers_path):
    """Обработка данных одного клиента"""
    try:
        transactions_df = pd.read_csv(transactions_path)
        transfers_df = pd.read_csv(transfers_path)

        analyzer = ClientAnalyzer(transactions_df, transfers_df)

        product_scores = analyzer.calculate_product_scores()

        best_product = max(product_scores.items(), key=lambda x: x[1])[0]

        push_text = analyzer.generate_push_notification(best_product)

        return {
            'client_code': analyzer.client_code,
            'product': best_product,
            'push_notification': push_text,
            'scores': product_scores  # Для отладки
        }

    except Exception as e:
        print(f"Ошибка обработки клиента: {e}")
        return None


def process_all_clients(base_path, num_clients=60):
    results = []

    for i in range(1, num_clients + 1):
        print(f"Обработка клиента {i}...")

        transactions_path = f"{base_path}/client_{i}_transactions_3m.csv"
        transfers_path = f"{base_path}/client_{i}_transfers_3m.csv"

        try:
            result = process_client(transactions_path, transfers_path)
            if result:
                results.append({
                    'client_code': result['client_code'],
                    'product': result['product'],
                    'push_notification': result['push_notification']
                })
        except FileNotFoundError:
            print(f"Файлы для клиента {i} не найдены")
            continue

    results_df = pd.DataFrame(results)
    return results_df



if __name__ == "__main__":
    base_path = "."

    # Обработка всех клиентов
    print("Начинаем обработку клиентов...")
    final_results = process_all_clients(base_path, num_clients=60)

    output_file = "personalized_recommendations.csv"
    final_results.to_csv(output_file, index=False, encoding='utf-8')

    print(f"Обработка завершена! Результаты сохранены в {output_file}")
    print(f"Обработано клиентов: {len(final_results)}")

    # Показать первые несколько результатов
    print("\nПервые 5 рекомендаций:")
    print(final_results.head().to_string(index=False))