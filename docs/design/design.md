# constraint

The core of `constraint` will be a meta-interpreter designed for running long
term queries that are mean to be run over days, weeks, or even months,
potentially involving real world interactions and constraint solving.  The goal
is to integrate with agentic AI systems to gradually build a knowledge base of
solvable patterns that may require a mix of human and machine intelligence to
resolve, and automate the parts that can be in an attempt to create
sophisticated reusable problem solving agents.

# Implementation

The initial implementation will be in Python, using Janus-SWI to run a Prolog
interpreter internally.  The meta-interpreter potentially takes a knowledge
base of observed and desirable facts, as well as "currently executing query" (a
remaining resolvent stack)

# Fact Databases
 
RocksDB will be used as the first layer fact databse engine.  A system will be
implemented with predicates in Prolog and functions in Python to store and
retreieve terms.  This will be the primary layer for complex synchronization
between Python and Janus-SWI.
 
Other longer term persistence layers will be added later, candidates are:

- PostgreSQL with a custom schema for storing Prolog terms
- TermiusDB (a graph database for Prolog terms)

The goal is to have term storage and retrieval be relatively seamless for the user between an backend.

The proposed predicates are
- `store(+Term, -Ref)` and `ref(+Ref, -Term)`, where `Ref` is currently somewhat opaque identifier that can be used to retrieve the term later.
    - some term (particular non-complex ground terms) are easily transferred between Python and Janus, so `Ref` may actually be a term containing information about how to retrieve the term later.
    - Regardless, users should not have to care about the details the implemntation of the `ref` predicate.

# Future Directions
 
- The core loop of a constraint project is:
    - Layer a set of facts (observed, desirable, etc)
        - These should be queryable from whatever datastores the user wants
    - Set up an inital query (resolvent stack with one goal basically )
    - Run the meta-interpreter to try to resolve the query
        - The meta-interpreter will continue until it is asked to pause, or it reaches a solution or dead end
        - The state is saved to disk so it can be resumed later, and the user potentially resolves some subgoals manually
