

# Threshold values

MIN_TEST_R2 = 0.85                                              
MAX_TEST_MAE = 0.35                                  
MAX_TEST_RMSE = 0.50     

# Khud ka Exception -> easy to differentite between normal and Gate error
class GateFailedError(Exception):
    pass

def gate(stats:dict):
    train_stats = stats['train']
    test_stats = stats['test']

    if abs(train_stats['r2'] - test_stats['r2']) < 0.15:

        if (test_stats['r2'] > MIN_TEST_R2) and (test_stats['mae'] < MAX_TEST_MAE) and (test_stats['rmse'] < MAX_TEST_RMSE):
            return True
        raise GateFailedError("Model is Under performing")

    raise GateFailedError("Model is Overfitting")