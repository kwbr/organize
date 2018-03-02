import logging
from collections import namedtuple

import yaml

from . import actions, filters
from .utils import Path, first_key, flatten

logger = logging.getLogger(__name__)
Rule = namedtuple('Rule', 'filters actions folders')


class Config:

    def __init__(self, config: dict):  # type: (dict)
        self.config = config

    @classmethod
    def parse_yaml(cls, config: str) -> dict:
        try:
            return yaml.load(config)
        except yaml.YAMLError as e:
            raise cls.ParsingError(e)

    @classmethod
    def from_string(cls, config: str) -> 'Config':
        return cls(cls.parse_yaml(config))

    @classmethod
    def from_file(cls, path: Path) -> 'Config':
        with path.open() as f:
            return cls.from_string(f.read())

    def yaml(self) -> str:
        if 'rules' not in self.config:
            raise self.NoRulesFoundError()
        data = {'rules': self.config['rules']}
        yaml.Dumper.ignore_aliases = lambda self, data: True
        return yaml.dump(data, default_flow_style=False, default_style=None)

    @staticmethod
    def parse_folders(rule_item):
        # the folder list is flattened so we can use encapsulated list
        # definitions in the config file.
        yield from flatten(rule_item['folders'])

    def _get_filter_class_by_name(self, name):
        try:
            return getattr(filters, name)
        except AttributeError as e:
            raise self.Error('%s is no valid filter' % name) from e

    def _get_action_class_by_name(self, name):
        try:
            return getattr(actions, name)
        except AttributeError as e:
            raise self.Error('%s is no valid action' % name) from e

    @staticmethod
    def _class_instance_with_args(Cls, args):
        if args is None:
            return Cls()
        elif isinstance(args, list):
            return Cls(*args)
        elif isinstance(args, dict):
            return Cls(**args)
        return Cls(args)

    def instantiate_filters(self, rule_item):
        # filter list can be empty
        try:
            filter_list = rule_item['filters']
        except KeyError:
            return
        if not filter_list:
            return
        if not isinstance(filter_list, list):
            raise self.FiltersNoListError()

        for filter_item in filter_list:
            # filter with arguments
            if filter_item is None:
                yield None
            elif isinstance(filter_item, dict):
                name = first_key(filter_item)
                args = filter_item[name]
                filter_class = self._get_filter_class_by_name(name)
                yield self._class_instance_with_args(filter_class, args)
            # only given filter name without args
            elif isinstance(filter_item, str):
                name = filter_item
                filter_class = self._get_filter_class_by_name(name)
                yield filter_class()
            else:
                raise self.Error('Unknown filter: %s' % filter_item)

    def instantiate_actions(self, rule_item):
        action_list = rule_item['actions']
        if not isinstance(action_list, list):
            raise self.ActionsNoListError()

        for action_item in action_list:
            if isinstance(action_item, dict):
                name = first_key(action_item)
                args = action_item[name]
                action_class = self._get_action_class_by_name(name)
                yield self._class_instance_with_args(action_class, args)
            elif isinstance(action_item, str):
                name = action_item
                action_class = self._get_action_class_by_name(name)
                yield action_class()
            else:
                raise self.Error('Unknown action: %s' % action_item)

    @property
    def rules(self):  # type: () -> List[Rule]:
        """:returns: A list of instantiated Rules
        """
        if 'rules' not in self.config:
            raise self.NoRulesFoundError()
        result = []
        for i, rule_item in enumerate(self.config['rules']):
            rule_folders = list(self.parse_folders(rule_item))
            rule_filters = list(self.instantiate_filters(rule_item))
            rule_actions = list(self.instantiate_actions(rule_item))

            if not rule_folders:
                logger.warning('No folders given for rule %s!', i + 1)
            if not rule_filters:
                logger.warning('No filters given for rule %s!', i + 1)
            if not rule_actions:
                logger.warning('No actions given for rule %s!', i + 1)

            rule = Rule(
                folders=rule_folders,
                filters=rule_filters,
                actions=rule_actions)
            result.append(rule)
        return result

    class Error(Exception):
        pass

    class NoRulesFoundError(Error):
        def __str__(self):
            return "No 'rules' found in configuration file"

    class ParsingError(Error):
        pass

    class NoFoldersFoundError(Error):
        pass

    class NoFiltersFoundError(Error):
        pass

    class NoActionsFoundError(Error):
        pass

    class FiltersNoListError(Error):
        def __str__(self):
            return 'Please specify your filters as a YAML list'

    class ActionsNoListError(Error):
        def __str__(self):
            return 'Please specify your actions as a YAML list'
