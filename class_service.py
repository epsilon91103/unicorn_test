from abc import ABCMeta, abstractmethod


class BaseService(metaclass=ABCMeta):
    """
    Service for working with currencies
    """
    @abstractmethod
    def parse_currencies(self):
        """
        Getting up-to-date currency information
        :return:
        """
        pass

    @abstractmethod
    def print_currency(self):
        """
        Information output if necessary
        :return:
        """
        pass

    @abstractmethod
    def start_service(self):
        """
        Service launch
        :return:
        """
        pass
