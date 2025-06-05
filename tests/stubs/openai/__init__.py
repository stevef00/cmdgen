class OpenAI:
    def __init__(self, *args, **kwargs):
        pass
    class responses:
        @staticmethod
        def create(*args, **kwargs):
            raise NotImplementedError("OpenAI API is not available in test env")
