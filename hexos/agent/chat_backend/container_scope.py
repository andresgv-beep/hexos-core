"""Make global and filtered container observations distinguishable before SSH."""


def resolve(args):
    args = dict(args)
    scope = args.pop('scope', None)
    if args.get('section') != 'containers':
        if scope is not None:
            raise ValueError('scope solo se admite con section=containers')
        return args, None
    name = args.get('container')
    if scope not in (None, 'all', 'name'):
        raise ValueError('scope debe ser all o name')
    if scope == 'all' and name is not None:
        raise ValueError('Para todos usa scope=all y omite container. Para un nombre usa scope=name.')
    if scope == 'name' and not name:
        raise ValueError('scope=name necesita container')
    if scope is None and name and name.casefold() in ('all', 'todos', '*'):
        raise ValueError('container es un filtro de nombre, no significa todos. Usa scope=all sin container; '
                         'si el nombre real es ese, usa scope=name y container.')
    return args, dict(kind='name_filter' if name else 'all', name=name,
                      covers_all_containers=not bool(name))
