"""
Module containing functions for representing a Ruleset using a hierarchical
tree.
"""

from collections import defaultdict
from lucid.rules.clause import ConjunctiveClause
from lucid.rules.rule import Rule
from lucid.rules.ruleset import Ruleset


################################################################################
## HTML/SVG Construction Helper Functions
################################################################################

def _htmlify(s):
    """
    Turn the given string into HTML by substituting special characters in it
    with their corresponding HTML codes.
    """
    for plain, html_code in [
        ("<=", "&leq;"),
        (">=", "&geq;"),
    ]:
        s = s.replace(plain, html_code)
    return s


################################################################################
## Hierarchical Tree Construction Methods
################################################################################


def _get_term_counts(ruleset):
    """
    Generates a frequency distribution of all the terms in the rule set.

    :param Ruleset ruleset: The ruleset whose term distribution we want to
        obtain.

    :return Tuple[List[Term], Dict[Term, int]]: a tuple containing first the
        list of all used terms in the rule set sorted in descended order of
        use and a dictionary mapping each term to its corresponding count.
    """
    num_used_rules_per_term_map = defaultdict(int)
    all_terms = set()
    for rule in ruleset.rules:
        for clause in rule.premise:
            for term in clause.terms:
                all_terms.add(term)
                num_used_rules_per_term_map[term] += 1

    # Make sure we display most used rules first
    used_terms = sorted(
        list(all_terms),
        key=lambda x: -num_used_rules_per_term_map[x],
    )
    return used_terms, num_used_rules_per_term_map


def _partition_ruleset(ruleset, term):
    """
    Partitions rule set `ruleset` into two rule sets (R1, R2) using term `term`
    such that R1 will contain all rules in `ruleset` that use term `term` in
    their premise and R2 will contain all other rules. All the rules in R1 will
    be modified so that they do not explicitly use `term` in their premises any
    more.

    This function is used for creating our visualization of the rule sets as
    trees by greedily grouping them according to the most used terms.

    :param Ruleset ruleset: The rule set we will partition.
    :param Term term: The term we want to partition the ruleset with.
    """

    # This will be the equivalent of R1
    contain_ruleset = Ruleset(
        rules=set(),
        feature_names=ruleset.feature_names,
        output_class_names=list(ruleset.output_class_map.keys()),
        regression=ruleset.regression,
    )

    # This will be the equivalent of R2
    disjoint_ruleset = Ruleset(
        rules=set(),
        feature_names=ruleset.feature_names,
        output_class_names=list(ruleset.output_class_map.keys()),
        regression=ruleset.regression,
    )
    for rule in ruleset.rules:
        for clause in rule.premise:
            found_term = False
            for c_term in clause.terms:
                if c_term == term:
                    found_term = True
                    break
            if found_term:
                # Then we found the term that we are looking for in this
                # rule! That means we will add it while also modifying it so
                # that the term is not included in its premise
                contain_ruleset.rules.add(Rule(
                    premise=set([
                        ConjunctiveClause(
                            terms=set(
                                [t for t in clause.terms if t != term]
                            ),
                            confidence=clause.confidence,
                            score=clause.score,
                        ),
                    ]),
                    conclusion=rule.conclusion,
                ))
            else:
                # Then add this guy into the disjoint ruleset
                disjoint_ruleset.rules.add(Rule(
                    premise=set([clause]),
                    conclusion=rule.conclusion,
                ))

    return contain_ruleset, disjoint_ruleset


def _extract_hierarchy_node(ruleset, dataset=None, merge=False):
    """
    Recursive function to produce a D3 Hierarchical Tree structure from the
    given rule set.

    This tree will be generated by producing branches in a greedy fashion such
    that most commonly used terms are selected first for generating early split
    nodes in the tree.
    Leaf nodes in the graph correspond to rules in the ruleset in a one-to-one
    fashion and each split node corresponds to a term used in the rule set.

    Note that, in contrast to decision trees, this will not be a binary tree by
    rather an n-ary tree.

    Each intermediate node in the resulting tree has the following fields:
        "name": an HTML name of this node containing a string version of
                 the condition it is splitting on.
        "children": a list of children nodes to this split node

    Each leaf node in the resulting tree in return will have the following
    fields:
        "name": an HTML string representing the conclusion of the rule ended
                by the leaf node.
        "children": an empty list representing the fact that this is a leaf
                    node.
        "score": a float representing the score of the rule represented by
                 this leaf node.

    :param Ruleset ruleset: The ruleset object we want to extract a D3
        hierarchical tree from.
    :param DatasetDescriptor dataset: An optional dataset descriptor for the
        given rule set which can help with annotations during visualization.
    :param bool merge: Whether or not we want to series of branches with only
        one child into a single child with a longer premise or not.
    """
    if not len(ruleset):
        return []
    if len(ruleset) == 1:
        # [BASE CASE]
        # Then simply output this rule (which is expected to have exactly one
        # clause)
        rule = next(iter(ruleset.rules))
        clause = next(iter(rule.premise)) if len(rule.premise) else None
        conclusion_node = {
            "name": _htmlify(str(rule.conclusion)),
            "children": [],
            "score": clause.score if clause is not None else 0,
        }
        if (clause is not None) and len(clause.terms):
            if merge:
                # Then we still have some terms left but we will not partition
                # on them as it will simply generate a chain
                return [
                    {
                        "name": _htmlify(" AND ".join(
                            map(
                                lambda x: x.to_cat_str(dataset)
                                if dataset is not None else str(x),
                                clause.terms
                            )
                        )),
                        "children": [conclusion_node],
                    },
                ]
            else:
                first = None
                current = None
                for term in clause.terms:
                    if current is None:
                        current = {
                            "name": _htmlify(
                                term.to_cat_str(dataset)
                                if dataset is not None else str(term)
                            ),
                            "children": [],
                        }
                        first = current
                    else:
                        next_elem = {
                            "name": _htmlify(
                                term.to_cat_str(dataset)
                                if dataset is not None else str(term)
                            ),
                            "children": [],
                        }
                        current["children"].append(next_elem)
                        current = next_elem
                # Finally add the conclusion
                current["children"].append(conclusion_node)
                return [first]

        # Else this is our terminal case and we add the conclusion node and
        # nothing else
        return [conclusion_node]

    # [RECURSIVE CASE]

    # Sort our nodes by the greedy metric of interest
    sorted_terms, term_count_map = _get_term_counts(
        ruleset=ruleset,
    )

    # Look at the first little bastard as this is
    # the best split in order
    next_term = sorted_terms[0]
    # Partition our ruleset around the current term
    contain_ruleset, disjoint_ruleset = _partition_ruleset(
        ruleset=ruleset,
        term=next_term,
    )

    # Construct the node for this term recursively by including it
    # in the exclude list
    next_node = {
        "name": _htmlify(
            next_term.to_cat_str(dataset)
            if dataset is not None else str(next_term)
        ),
        "children": _extract_hierarchy_node(
            ruleset=contain_ruleset,
            dataset=dataset,
            merge=merge,
        ),
    }

    # And return the result of adding this guy to our list and the
    # children resulting from the rules that do not contain it
    return [next_node] + _extract_hierarchy_node(
        ruleset=disjoint_ruleset,
        dataset=dataset,
        merge=merge,
    )


def _compute_tree_properties(tree, depth=0, merge=False):
    """
    Annotates the given D3 Hierarchical tree node representing a rule set with
    annotations concerning properties of its children. It does this in a
    recursive fashion by annotating nodes in the entire subtree rooted at
    `tree`.

    :param d3.Node tree: Current node in D3's hierarchical tree which we will
        annotate.
    :param int depth: Current depth of the given node.
    :param bool merge: Whether or not we want to series of branches with only
        one child into a single child with a longer premise or not.
    """
    tree["depth"] = depth
    if len(tree["children"]) == 0:
        # Then this is a leaf!
        tree["num_descendants"] = 0
        tree["class_counts"] = {
            tree["name"]: 1,
        }
        return tree
    if (depth != 0) and len(tree["children"]) == 1 and merge and (
        len(tree["children"][0]["children"]) != 0
    ):
        # Then we can collapse this into a single node for ease of visibility
        # in this graph
        old_child = tree["children"][0]
        tree["children"] = old_child["children"]
        tree["name"] += " AND " + old_child["name"]

    # Else proceed recursively
    tree["num_descendants"] = 0
    tree["class_counts"] = {}
    class_counts = tree["class_counts"]
    for child in tree["children"]:
        child = _compute_tree_properties(child, depth=(depth + 1))
        tree["num_descendants"] += child["num_descendants"] + 1
        for class_name, count in child["class_counts"].items():
            class_counts[class_name] = count + class_counts.get(
                class_name,
                0
            )
    return tree


def ruleset_hierarchy_tree(ruleset, dataset=None, merge=False):
    """
    Given a Ruleset `ruleset`, this method will produce a D3 Hierarchical tree
    representation of the same ruleset using a greedy n-ary decision tree
    induction where we group individual rules in the rule set using the most
    commonly used terms found across all rules.

    :param Ruleset ruleset: The ruleset object we want to extract a D3
        hierarchical tree from.
    :param DatasetDescriptor dataset: An optional dataset descriptor for the
        given rule set which can help with annotations during visualization.
    :param bool merge: Whether or not we want to series of branches with only
        one child into a single child with a longer premise or not.
    """
    tree = {
        "name": "ruleset",
        "children": _extract_hierarchy_node(
            ruleset=ruleset,
            dataset=dataset,
            merge=merge,
        ),
    }
    return _compute_tree_properties(tree, merge=merge)
