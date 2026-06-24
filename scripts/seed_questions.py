"""Seed the question bank with initial interview questions."""
import sys
import os

# Force UTF-8 on Windows for Chinese character output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.ai.rag.ingestion import ingest_questions

# Pre-written interview questions covering common tech stacks
QUESTIONS = [
    # Python Basics
    {
        "question": "解释 Python 中的装饰器（decorator）原理，并写一个计算函数执行时间的装饰器",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Python", "decorator", "functional programming"],
        "reference_answer": "装饰器本质是闭包，接收函数返回新函数。使用 @wraps 保留元信息。"
    },
    {
        "question": "Python 中生成器（generator）和迭代器（iterator）的区别是什么？什么场景用生成器？",
        "type": "technical",
        "difficulty": "easy",
        "topics": ["Python", "generator", "iterator"],
        "reference_answer": "生成器是特殊的迭代器，使用 yield 惰性生成值，节省内存。"
    },
    {
        "question": "解释 Python 的 GIL（全局解释器锁），多线程在 Python 中是否有用？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Python", "GIL", "concurrency"],
        "reference_answer": "GIL 限制同一时刻只有一个线程执行字节码。IO密集型多线程仍有用，CPU密集型用多进程。"
    },
    {
        "question": "Python 中 `__new__` 和 `__init__` 的区别是什么？各自的调用时机？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["Python", "OOP", "internals"],
        "reference_answer": "__new__ 是类方法，创建实例对象；__init__ 是实例方法，初始化对象属性。先 __new__ 后 __init__。"
    },
    {
        "question": "什么是协程（coroutine）？Python 中 asyncio 的工作原理是什么？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["Python", "asyncio", "coroutine"],
        "reference_answer": "协程是用户态轻量级线程，通过事件循环调度，await 挂起等待，不阻塞线程。"
    },

    # Python Advanced
    {
        "question": "Python 中如何实现单例模式？至少给出三种不同的实现方式",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Python", "design patterns", "singleton"],
        "reference_answer": "模块单例、__new__控制、装饰器、元类等方式。"
    },
    {
        "question": "解释 Python 的垃圾回收机制，引用计数和分代回收是如何配合工作的？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["Python", "GC", "memory management"],
        "reference_answer": "引用计数为主（立即释放），分代回收为辅（处理循环引用），分0/1/2三代。"
    },

    # FastAPI & Web
    {
        "question": "FastAPI 中依赖注入（Depends）的工作原理是什么？它有什么优势？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["FastAPI", "DI", "Python web"],
        "reference_answer": "通过参数签名和类型注解自动解析依赖，支持嵌套依赖、缓存和覆盖。"
    },
    {
        "question": "RESTful API 设计中，如何处理分页？比较基于偏移量和基于游标的分页方式",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["API design", "pagination", "REST"],
        "reference_answer": "偏移量分页简单但不稳定，游标分页性能好但在大数据集上实时性好。"
    },

    # Database
    {
        "question": "MySQL 中索引的底层数据结构是什么？为什么用 B+ 树而不是 B 树或哈希表？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["MySQL", "index", "B+ tree"],
        "reference_answer": "B+树所有数据在叶子节点，叶子节点形成链表，适合范围查询和顺序扫描。"
    },
    {
        "question": "什么是数据库事务的 ACID 特性？MySQL 中隔离级别有哪些？分别解决什么问题？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["MySQL", "transaction", "ACID"],
        "reference_answer": "四个隔离级别：读未提交、读已提交、可重复读、串行化。解决脏读、不可重复读、幻读。"
    },
    {
        "question": "SQL 和 NoSQL 数据库各有什么适用场景？什么情况会选择 Redis 而不是 MySQL？",
        "type": "technical",
        "difficulty": "easy",
        "topics": ["database", "SQL", "NoSQL", "Redis"],
        "reference_answer": "SQL 适合关系型数据和高一致性要求，NoSQL 适合非结构化/高并发/低延迟场景。"
    },

    # Redis
    {
        "question": "Redis 的过期策略有哪些？它们分别如何工作？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Redis", "cache", "expiration"],
        "reference_answer": "惰性删除（访问时检查）+ 定期删除（每100ms随机抽样）。还有内存淘汰策略（LRU/LFU等）。"
    },
    {
        "question": "如何用 Redis 实现分布式锁？使用 SETNX 有什么潜在问题？Redlock 算法解决了什么？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["Redis", "distributed lock", "Redlock"],
        "reference_answer": "SETNX + 过期时间 + 唯一 value 防止误删。Redlock 在多个 Redis 实例上获取锁，多数成功才算获取。"
    },

    # Docker & DevOps
    {
        "question": "Docker 镜像的分层结构是如何工作的？为什么分层设计能加速构建和部署？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Docker", "container", "layer"],
        "reference_answer": "每层只读，Copy-on-Write，相同层可复用。Dockerfile 每行指令创建一层。"
    },
    {
        "question": "Docker 和虚拟机的主要区别是什么？从操作系统层面解释容器隔离的实现原理",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["Docker", "VM", "isolation"],
        "reference_answer": "容器共享宿主机内核，通过 namespace 隔离进程/网络/文件系统，cgroup 限制资源。"
    },

    # System Design
    {
        "question": "设计一个高并发的短链接服务（URL Shortener），需要考虑哪些核心组件？",
        "type": "system_design",
        "difficulty": "easy",
        "topics": ["system design", "URL shortener", "scalability"],
        "reference_answer": "ID生成服务、缓存层、关系存储、重定向服务。ID生成考虑 Snowflake 或 base62 编码。"
    },

    # Behavioral
    {
        "question": "描述一个你在项目中遇到的最大技术挑战，你是如何解决的？学到了什么？",
        "type": "behavioral",
        "difficulty": "medium",
        "topics": ["problem solving", "learning", "technical challenge"],
        "reference_answer": "STAR: Situation-背景, Task-任务, Action-行动, Result-结果。强调具体措施和量化成果。"
    },
    {
        "question": "如果你加入一个新团队，发现代码库质量很差（缺乏测试、技术债严重），你会怎么做？",
        "type": "behavioral",
        "difficulty": "medium",
        "topics": ["team collaboration", "code quality", "initiative"],
        "reference_answer": "渐进式改进，先理解现状和背景，提出优先级排序，通过示范和文档推动改进。"
    },
]

# Additional questions for JavaScript/TypeScript
JS_QUESTIONS = [
    {
        "question": "JavaScript 中闭包（closure）是什么？请举例说明闭包的实际应用场景",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["JavaScript", "closure", "scope"],
        "reference_answer": "闭包是函数能访问其外部作用域变量的机制，常用于数据封装和回调。"
    },
    {
        "question": "Vue 3 的响应式系统和 Vue 2 有什么本质区别？Proxy 相比 Object.defineProperty 有什么优势？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Vue", "reactivity", "Proxy"],
        "reference_answer": "Proxy 能拦截数组变化和属性添加删除，不需要预先定义所有属性，性能更好。"
    },
    {
        "question": "React 中 useEffect 的依赖数组为空、不传、传依赖有什么区别？",
        "type": "technical",
        "difficulty": "easy",
        "topics": ["React", "useEffect", "hooks"],
        "reference_answer": "空数组：只执行一次；不传：每次渲染都执行；传依赖：依赖变化时执行。"
    },
    {
        "question": "TypeScript 中 type 和 interface 的区别是什么？什么时候用哪个？",
        "type": "technical",
        "difficulty": "easy",
        "topics": ["TypeScript", "type system"],
        "reference_answer": "interface 可被合并声明，type 更灵活（联合/交叉类型）。优先用 interface，需要联合类型时用 type。"
    },
]

# General AI/ML questions
AI_QUESTIONS = [
    {
        "question": "解释 RAG（Retrieval-Augmented Generation）的完整工作流程，以及它相比纯 LLM 的优势",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["RAG", "LLM", "vector search"],
        "reference_answer": "文档切分→Embedding→向量存储→检索→增强Prompt→生成。优势：知识更新、减少幻觉、可溯源。"
    },
    {
        "question": "什么是 Prompt Engineering？分享几个你常用的 Prompt 技巧",
        "type": "technical",
        "difficulty": "easy",
        "topics": ["Prompt Engineering", "LLM"],
        "reference_answer": "角色设定、Few-shot、Chain-of-Thought、结构化输出、分步指令。"
    },
    {
        "question": "如何评估一个 LLM 应用的质量？有哪些常用的评估指标和方法？",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["LLM evaluation", "metrics"],
        "reference_answer": "准确率、相关性、流畅度；人工评估、LLM-as-judge、RAGAS 框架等。"
    },
    {
        "question": "什么是 Agent 的 Tool Use / Function Calling？描述它的工作原理",
        "type": "technical",
        "difficulty": "medium",
        "topics": ["Agent", "Tool Use", "Function Calling"],
        "reference_answer": "LLM 根据用户意图决定调用哪个工具，生成结构化调用参数，执行后将结果返回 LLM 继续推理。"
    },
    {
        "question": "MCP（Model Context Protocol）解决了什么问题？和传统的 Function Calling 有什么不同？",
        "type": "technical",
        "difficulty": "hard",
        "topics": ["MCP", "Agent", "protocol"],
        "reference_answer": "MCP 标准化了 LLM 与外部工具/资源的交互协议，解耦了 Agent 和工具，支持发现、调用、安全控制。"
    },
]


def main():
    all_questions = QUESTIONS + JS_QUESTIONS + AI_QUESTIONS
    print(f"Seeding {len(all_questions)} questions into question_bank...")
    count = ingest_questions(all_questions, clear_existing=True)
    print(f"Successfully seeded {count} questions!")


if __name__ == "__main__":
    main()
