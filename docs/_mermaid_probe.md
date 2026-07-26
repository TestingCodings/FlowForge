# Mermaid probe

Temporary. Isolates whether GitHub's mermaid renderer works on this repo at
all, versus the architecture diagram's syntax being at fault.

## 1. Minimal graph (no subgraphs, no classDef, no labels on edges)

```mermaid
graph TD
    A[Start] --> B[Middle]
    B --> C[End]
```

## 2. Adds a subgraph with a quoted label

```mermaid
graph TB
    subgraph one["Group one"]
        X[Node X]
    end
    X --> Y[Node Y]
```

## 3. Adds classDef/class

```mermaid
graph LR
    P[Alpha] --> Q[Beta]
    classDef c1 fill:#e1f5ff,stroke:#0284c7
    class P c1
```

## 4. Adds a br tag inside a label

```mermaid
graph LR
    R["Line one<br/>Line two"] --> S[Plain]
```
