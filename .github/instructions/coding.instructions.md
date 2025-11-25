---
applyTo: '**'
---

# Coding Standards & Best Practices

Follow these professional coding standards to ensure maintainable, optimized, and robust code:

---

## Core Principles

### 1. DRY (Don't Repeat Yourself)
- **Before adding code**: Check if similar functionality already exists
- **Refactor duplicated code** into reusable functions, classes, or modules
- **Example**: If adding a property to an object requires changes in 50+ places, consider:
  - Making the property optional in constructors with default values
  - Using factory methods or builder patterns
  - Implementing proper inheritance or composition

### 2. SOLID Principles
- **Single Responsibility**: Each class/function has one reason to change
- **Open/Closed**: Open for extension, closed for modification
- **Liskov Substitution**: Derived classes must be substitutable for base classes
- **Interface Segregation**: Create focused, cohesive interfaces
- **Dependency Inversion**: Depend on abstractions, not concrete implementations

### 3. Code Optimization Rules
- **Post-Implementation Review**: After each code change, review for optimization opportunities
- **Parameter Reduction**: If a function has 3+ parameters, consider using configuration objects
- **Constructor Optimization**: When adding properties, check if they can be:
  - Optional with sensible defaults
  - Derived from other properties
  - Set through fluent interfaces or builders
- **Pattern Recognition**: Look for emerging patterns that suggest the need for:
  - Base classes or interfaces
  - Factory methods
  - Strategy patterns
  - Configuration-driven approaches

---

## Implementation Standards

### 4. Clean Code Practices
- **Meaningful Names**: Use descriptive, intention-revealing names
- **Small Functions**: Keep methods under 20 lines, preferably 5-10 lines
- **Single Level of Abstraction**: Each function should work at one level of abstraction
- **Minimize Parameters**: Aim for 0-2 parameters; use objects for complex parameter sets
- **Pure Functions**: Prefer functions without side effects when possible

### 5. Error Handling & Resilience
- **Explicit Error Handling**: Don't hide exceptions; handle them appropriately
- **Fail Fast**: Validate inputs early and provide clear error messages
- **Defensive Programming**: Check preconditions and postconditions
- **Graceful Degradation**: Design for partial failures

### 6. Performance & Efficiency
- **Lazy Loading**: Don't compute values until needed
- **Caching Strategy**: Cache expensive computations and frequently accessed data
- **Resource Management**: Properly dispose of resources (using statements, try-finally blocks)
- **Algorithm Efficiency**: Choose appropriate data structures and algorithms for the use case

---

## Quality Assurance

### 7. Code Review Checklist
After implementing changes, verify:
- [ ] No code duplication exists
- [ ] New patterns can be generalized for future use
- [ ] Performance impact is acceptable
- [ ] Error handling is comprehensive
- [ ] Code is self-documenting or well-commented
- [ ] Unit tests cover new functionality

### 8. Refactoring Triggers
Consider refactor when you notice:
- **Repeated Code Blocks**: 3+ similar implementations
- **Long Parameter Lists**: 6+ parameters in methods
- **Complex Conditionals**: Nested if/else or switch statements
- **Large Classes/Methods**: Classes with 10+ methods or methods with 30+ lines
- **Primitive Obsession**: Using primitives instead of value objects

---

## Architecture Guidelines

### 9. Modularity & Separation of Concerns
- **Layer Separation**: Clear boundaries between UI, business logic, and data access
- **Dependency Injection**: Use DI containers for managing dependencies
- **Configuration Management**: Externalize configuration from code
- **Event-Driven Design**: Use events for loose coupling between components

### 10. Future-Proofing
- **Extensibility**: Design extension points for likely future changes
- **Backward Compatibility**: Consider impact on existing clients
- **Version Strategy**: Plan for versioning of APIs and interfaces
- **Documentation**: Keep code documentation current with changes

---

## Optimization Decision Tree

When adding features, ask:
1. **Does this exist already?** → Reuse or extend existing code
2. **Will this be needed elsewhere?** → Create reusable component
3. **Can this be made configurable?** → Use configuration over hard-coding
4. **Does this introduce coupling?** → Consider dependency injection or events
5. **Is this testable in isolation?** → Refactor for better testability

---

## Additional Best Practices

### Code Organization
- **File Structure**: Group related functionality together
- **Naming Conventions**: Follow language-specific conventions consistently
- **Import Management**: Keep imports organized and remove unused ones
- **Comment Strategy**: Write comments for "why" not "what"

### Testing Strategy
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete user workflows
- **Test Coverage**: Aim for meaningful coverage, not just high percentages

### Documentation
- **API Documentation**: Document public interfaces and expected behaviors
- **README Files**: Provide clear setup and usage instructions
- **Code Comments**: Explain complex business logic and algorithms
- **Change Logs**: Document breaking changes and new features