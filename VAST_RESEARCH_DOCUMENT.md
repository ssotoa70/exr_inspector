# VAST DataEngine and VAST DataBase Specifications Research Document

**Research Date:** February 6, 2026
**Version Researched:** 54.5 and Latest (2.0.2 SDK)
**Research Scope:** VAST DataEngine serverless functions, VAST DataBase SQL and Vector capabilities

---

## Executive Summary

This document provides comprehensive specifications for VAST DataEngine serverless functions and VAST DataBase capabilities (SQL and Vector). Information was gathered from the official VAST Knowledge Base, SDK documentation, blog posts, and technical resources. The VAST platform is a unified AI Operating System that combines storage (DataStore), database (DataBase), serverless compute (DataEngine), and vector capabilities (Vector Search, InsightEngine).

---

## 1. VAST DataEngine Specifications

### 1.1 Function Execution Architecture

**Execution Model:**
- Lightweight, containerized Python functions that execute directly where data resides
- Stateless containers deployed on CNodes (compute nodes)
- Serverless execution environment accessible via Python SDK and container execution framework
- Orchestrates execution across federated VAST clusters while minimizing data movement

**Source:** [VAST DataEngine: Real-Time Compute Fabric for Data & AI - VAST Data](https://www.vastdata.com/platform/dataengine)

### 1.2 Function Timeout Limits

**Status:** Information Not Publicly Available in Documentation

The official VAST documentation does not specify explicit timeout limits for serverless function execution. This is a critical specification that should be requested from VAST support.

**Recommendation:** Contact VAST support or consult internal documentation for:
- Maximum execution time per function invocation
- Timeout configuration options
- Handling of long-running operations

**Sources Checked:**
- [VAST DataEngine specifications](https://www.vastdata.com/platform/dataengine)
- [VAST SDK Documentation](https://vastdb-sdk.readthedocs.io/)
- Knowledge Base articles

### 1.3 Concurrent Function Execution Limits

**Status:** Information Not Publicly Available in Documentation

The maximum number of concurrent function executions is not explicitly documented in public resources. This is essential for capacity planning and should be obtained from VAST.

**Recommendation:** Contact VAST support for:
- Maximum concurrent execution count
- Per-cluster limits
- Per-tenant limits
- Scaling behavior under load

### 1.4 Cold Start Behavior and Container Lifecycle

**Container Management:**
- Functions are packaged as Docker container images
- Images are pushed to private registries
- Images are registered in VAST platform's management interface
- Containers run on CNodes (compute cluster nodes)
- Architecture uses DASE (Disaggregated Shared-Everything) design for efficient resource utilization

**Execution Flow:**
1. User packages code and dependencies into standard Docker container image
2. Container image pushed to private registry
3. Image registered in VAST platform management interface
4. Execution triggered by events or schedules
5. Function executes in stateless container on available CNode

**Optimization Potential:**
The DASE architecture and NVMe-over-Fabrics connectivity eliminate need for data movement to compute, potentially reducing cold start overhead compared to traditional serverless platforms.

**Sources:**
- [VAST DataEngine blog](https://www.vastdata.com/blog/vast-dataengine-bringing-compute-to-your-data)
- [Glenn Klockwood VAST Documentation](https://www.glennklockwood.com/garden/VAST)

### 1.5 Function Memory Allocation Options

**Status:** Information Not Publicly Available in Documentation

Specific memory allocation options, limits, and configuration parameters are not documented in public resources.

**Recommended Information to Obtain:**
- Memory allocation range (minimum/maximum)
- Default memory allocation
- CPU-to-memory ratio options
- Memory oversubscription policies
- Out-of-memory handling

### 1.6 Supported Runtimes

**Python Support:**
- Python 3.10 through 3.13 explicitly supported (based on VAST DB SDK requirements)
- Primary programming model: Python functions
- Custom libraries and dependencies can be packaged in Docker containers

**Container Support:**
- Any containerized application can be packaged and deployed
- Standard Docker container format
- Custom, user-defined functions in any language (via containerization)

**Additional Language Support:**
Information suggests "any code or library can be packaged, deployed, and triggered natively within the platform," but specific runtime support is not explicitly documented.

**Source:** [VAST DB Python SDK Documentation](https://vastdb-sdk.readthedocs.io/)

### 1.7 Event Triggering Mechanisms

**Available Trigger Types:**

#### Schedule-Based Triggers
- Scheduled batch processing via cron-like scheduling
- Enables time-based function invocation

#### S3 Event Triggers
- Functions triggered by file arrival in S3-compatible storage
- VAST DataStore exposes S3-compatible object interface
- Automatic processing of files as they arrive in data lake
- Supports real-time event-driven data processing

#### Database Events
- Functions triggered by database operations (implied)
- Integration with DataBase table operations

**Event Processing Architecture:**
- Event Broker (Kafka-compatible) built on DataBase
- S3-interface-triggered events supported
- Platform handles scheduling, event detection, and resource allocation

**Quote:** "DataEngine provides three powerful building blocks: Functions (application code packaged as containers), Triggers (event sources that start your functions such as schedules or S3 events), and Pipelines (the orchestration layer that connects triggers to functions with intelligent resource management)."

**Sources:**
- [DataEngine overview](https://www.vastdata.com/blog/automation-with-vast-serverless-functions-in-dataengine)
- [VAST DASE architecture documentation](https://www.vastdata.com/platform/how-it-works)

### 1.8 Observability and Logging Capabilities

**Built-In Observability:**
- All telemetry and logs from functions automatically captured
- Logs streamed into VAST DataBase tables
- Rendered in UI for debugging and performance monitoring
- Queryable from CLI and API interface
- Logs, metrics, and execution traces captured
- Zero administration or setup required

**Debugging Support:**
- Traces available for performance analysis
- Integration with VAST DataBase for long-term analysis
- Queryable metrics and logs for post-execution analysis

**Monitoring Dashboard:**
- UI visualization of function execution
- Performance monitoring capabilities
- Built-in platform observability (no external tooling required)

**Quote:** "All telemetry and logs from your functions get streamed into VAST DataBase tables, which are then rendered in the UI as well as queryable from a CLI and API interface."

**Source:** [VAST DataEngine specifications](https://www.vastdata.com/platform/dataengine)

### 1.9 Error Handling and Retry Patterns

**Status:** Information Not Publicly Available in Documentation

Specific details about error handling, retry strategies, and failure modes are not explicitly documented.

**Information to Obtain from VAST:**
- Error types and exceptions available
- Retry mechanism availability and configuration
- Maximum retry count
- Exponential backoff support
- Dead letter queue handling
- Failure notifications

**SDK Error Module Available:**
- The Python SDK includes an `errors` module for exception handling
- Predicate pushdown filtering has specific error modes
- Transaction handling includes error scenarios

**Related Resource:** [VAST DB SDK Error Module](https://vastdb-sdk.readthedocs.io/)

### 1.10 Function Size and Code Limits

**Status:** Information Not Publicly Available in Documentation

No public documentation specifies:
- Maximum function code size
- Maximum container image size
- Deployment artifact limits
- Memory limits for function packages
- Dependency bundle size constraints

**Assumption Based on Container Model:**
- Likely inherited from Docker/OCI container standards
- Typical cloud platforms allow 250MB-1GB+ container images
- Should be confirmed with VAST support

---

## 2. VAST DataBase SQL Capabilities

### 2.1 Supported SQL Operations

**Core Operations:**

#### SELECT
- Full support for SELECT operations with column projection
- Predicate pushdown for efficient filtering
- Alias support and computed columns
- Aggregate functions support

#### INSERT
- Row insertion supported
- Column-based insertion (v1.4.0+)
- Batch insert operations via Python SDK
- PyArrow RecordBatch insertion

#### UPDATE
- Update operations for sorted tables (v1.3.8+)
- Row ID-based updates using special "$row_id" field (uint64 type)
- Support for updating subset of cells

#### DELETE
- Delete operations for sorted tables (v1.3.8+)
- Row ID-based deletion

**Query Features:**
- Complex filtering with multiple operators
- Result limiting and pagination
- Timestamp timezone support (v1.3.10+)
- Pattern matching (LIKE operations)
- Range queries (BETWEEN)
- NULL checks (IS NULL, IS NOT NULL)
- Set operations (IN, NOT IN)

**Source:** [VAST DB Python SDK CHANGELOG](https://vastdb-sdk.readthedocs.io/en/latest/)

### 2.2 Transaction Support (ACID Guarantees)

**ACID Compliance:**
- Fully ACID compliant platform
- Ensures efficiency, scalability, and reliability

**Transaction Requirements:**
- Every database-related operation requires an active transaction
- Transactions implemented as context managers in Python SDK
- Transaction must remain active during query execution and result fetching

**Multi-Modal Workload Support:**
- Unifies transactional and analytical workloads
- Writes in rows (perfect for transactions)
- Stores in columns (optimized for analytics)
- Supports both OLTP (Online Transaction Processing) and OLAP workloads

**Transaction Pattern:**
```python
# Standard transaction context manager pattern
with session.transaction() as txn:
    # Perform operations
    table.insert(data)
    results = table.select(predicates)
```

**Performance Characteristics:**
- Quote: "delivers up to 20x faster queries and 40x faster transactions"
- Single-ms latency mentioned
- Linear scaling to exabytes

**Sources:**
- [VAST DataBase specifications](https://www.vastdata.com/platform/database)
- [VAST DB SDK Documentation](https://vastdb-sdk.readthedocs.io/)

### 2.3 Available SQL Functions

#### Filtering and Predicate Operators

**Comparison Operators:**
- Less than: `<`
- Less than or equal: `<=`
- Equal: `==`
- Greater than: `>`
- Greater than or equal: `>=`
- Not equal: `!=`

**Set Operations:**
- Membership testing: `isin()`

**NULL Handling:**
- `isnull()` - NULL checks
- Negation support for NULL checks

**String Operations:**
- `startswith()` - Prefix matching
- `contains()` - Substring matching

**Data Type Support for Predicates:**
14 Arrow types support predicate pushdown:
- Integers (various sizes)
- Floating point numbers
- Decimals
- Strings (UTF8)
- Booleans
- Binary data
- Temporal types: date32, time32, time64, timestamp

#### Vector Operations

**Distance Functions (in SQL dialect via ADBC driver):**
- `array_cosine_distance` - Cosine similarity
- `array_distance` - Euclidean distance
- `array_negative_inner_product` - Negative inner product

**Query Integration:**
- Vector similarity queried via SQL with ADBC driver
- Similarity functions combined with categorical or bounded criteria
- Hybrid queries possible (vector + SQL filters)

**Sources:**
- [VAST DB Predicate Pushdown Documentation](https://vastdb-sdk.readthedocs.io/en/latest/docs/predicate.html)
- [Glenn Klockwood Vector Database Notes](https://glennklockwood.com/garden/VAST-vector-database)

**Important Limitation:** General SQL function documentation (aggregate functions, string functions, date/time functions, math functions) for VAST DataBase is not publicly available. Recommend consulting VAST documentation for complete function list.

### 2.4 Full-Text Search Capabilities

**Status:** Information Not Publicly Available in Documentation

Full-text search capabilities are not documented in public VAST resources. This is a significant gap if FTS is a requirement.

**Recommendation:** Verify with VAST support whether:
- Native full-text search is supported
- Text indexing capabilities available
- Search operator syntax
- Performance characteristics for text queries

### 2.5 Batch Operation Support

**Batch Insert Operations:**
- Multiple Parquet file imports supported (concurrent)
- Column-based insertion for multiple rows
- PyArrow RecordBatch insertion enables batch operations

**Query Result Processing:**
- Stream of PyArrow record batches
- Direct export to Parquet files
- DuckDB integration for post-processing
- Efficient columnar data handling

**Scalability:**
- Designed for efficient bulk imports
- Concurrent import capabilities

**Source:** [VAST DB SDK Documentation](https://vastdb-sdk.readthedocs.io/)

### 2.6 Query Timeout Limits

**Status:** Information Not Publicly Available in Documentation

Specific query timeout settings are not documented in public resources.

**Information to Obtain:**
- Default query timeout value
- Maximum configurable timeout
- Per-query timeout override capability
- Timeout behavior on long-running queries
- Handling of timeout errors

**Related Configuration:**
The SDK supports QueryConfig for query tuning with `num_sub_splits` parameter for controlling internal CNode concurrency, but timeout settings are not documented.

**Source:** [VAST DB Configuration Documentation](https://vastdb-sdk.readthedocs.io/en/latest/docs/config.html)

### 2.7 Query Performance Characteristics

**Single-CNode Tuning:**
- Query result scanning can be distributed across multiple endpoints
- Explicit CNode URLs can be listed (via VIPs or domain names)
- Load distribution across infrastructure nodes possible

**Internal Concurrency:**
- Control parallel processing within single CNode using `num_sub_splits`
- Higher internal CNode concurrency helps selective queries
- Single request can leverage multiple CNode cores through worker threads

**Data Format & Processing:**
- Columnar data organization in 32KB chunks
- Co-location of vectors, metadata, and raw content minimizes data hops
- Eliminates secondary fetches

**Performance Metrics (from marketing materials):**
- Quote: "20x faster queries and 40x faster transactions"
- Single-millisecond (1ms) latency
- Sub-second query response on real-time data
- No staging or lag

**Query Optimization:**
- Predicate pushdown filtering
- Column projection pushdown
- Efficient data access patterns

**Source:** [VAST DB Configuration](https://vastdb-sdk.readthedocs.io/en/latest/docs/config.html)

---

## 3. VAST DataBase Vector Capabilities

### 3.1 Vector Data Type Support

**Native Vector Column Type:**
- Vectors stored as vector column type within VAST DataBase
- Supported precision: float32 (confirmed minimum)
- Vector elements stored as ordered arrays
- Example: "five-element lists of float32" values

**Storage Architecture:**
- Vectors stored natively in VAST DataBase
- Co-located with structured metadata and unstructured content
- Single platform storage (no external indexes required)
- Treated as first-class data type

**Integration with SQL:**
- Vector columns queryable via standard SQL dialect
- ADBC (Arrow Database Connectivity) driver exposes SQL interface
- Hybrid queries combining vectors with relational data

**Source:** [Glenn Klockwood Vector Database Documentation](https://glennklockwood.com/garden/VAST-vector-database)

### 3.2 Vector Similarity Operators

**Supported Distance Metrics:**

#### Cosine Similarity
- Function: `array_cosine_distance`
- Best for: Text embeddings, direction-based similarity
- SQL queryable

#### Euclidean Distance
- Function: `array_distance`
- Best for: Geometric similarity, coordinate-based distance
- SQL queryable

#### Negative Inner Product
- Function: `array_negative_inner_product`
- Best for: Optimized inner product calculations
- SQL queryable

**Query Effort Configuration:**
- Configurable query effort to trade off between speed and precision
- Different precision levels can be tuned based on use case

**Quote:** "VAST supports multiple distance functions, including cosine similarity, Euclidean distance, and inner product, allowing you to choose the right metric for your specific use case."

**Source:** [VAST Vector Search Blog](https://www.vastdata.com/blog/vast-vector-search-the-right-foundation-for-real-time-ai)

### 3.3 Vector Index Types

**Status:** Partially Documented

**Confirmed Information:**
Vector indexing is performed automatically as part of the data ingestion path. The system builds:
- Vector indexes in real time
- Zone maps for data pruning
- Secondary indexes
- Sorted projections
- Precomputed materializations

**Index Optimization Features:**
- Early block pruning using compact columnar data chunks
- Acceleration of retrieval through intelligent index structures
- CPU fallback paths for consistency
- 32KB columnar chunk organization

**Not Explicitly Documented:**
- Specific index type names (HNSW, IVFFlat, etc.)
- Index configuration options
- Trade-offs between different index types
- Index size and memory requirements

**Note:** While pgvector and similar vector databases support HNSW and IVFFlat indexes with dimension limits of 2000, VAST's documentation does not explicitly specify which index types it uses. The architecture suggests custom optimization rather than standard pgvector implementations.

**Source:** [VAST Vector Search Architecture](https://www.vastdata.com/platform/how-it-works)

### 3.4 Vector Dimension Limits

**Status:** Information Not Publicly Available in Documentation

The maximum number of dimensions supported is not explicitly documented. This is a critical specification for embedding model selection.

**What We Know:**
- VAST supports "trillion-vector scale"
- No mention of dimension limits
- Designed for massive vector spaces
- Real-time indexing of any incoming data

**Information to Obtain from VAST:**
- Maximum vector dimensions supported
- Supported precision formats (float32, float64, etc.)
- Half-precision support
- Memory requirements per vector dimension
- Performance impact of high-dimensional vectors

**Related Note:** Standard pgvector supports up to 2000 dimensions with HNSW/IVFFlat indexes and up to 4000 with special halfvec type, but VAST's custom architecture may have different limits.

### 3.5 Vector Search Performance

**Scale Capabilities:**
- First and only vector database supporting trillion-vector scale
- Ability to search large vector spaces in constant time
- Sub-second search performance maintained at trillion-vector scale

**Throughput Characteristics:**
- Parallel transactional design enables real-time vector space updates
- All servers can search entire vector space in milliseconds for AI inferencing
- Linear throughput scaling as nodes are added
- Consistent performance from millions to trillions of vectors

**Query Performance:**
- Sub-second retrieval performance across massive datasets
- By default returns top 1,000 closest matches
- Each result resolves to full table row with metadata and original content
- No external system calls needed for result resolution

**Latency:**
- Millisecond-scale searches
- Real-time search performance maintained at scale
- No performance degradation from data size

**Architecture Benefits:**
- NVMe-over-Fabrics (NVMe-oF) delivers high-speed access across entire cluster
- Direct compute node access to all indexes via NVMe-oF
- Eliminates sharding overhead
- Real-time search across text, images, audio, and other modalities

**Quote:** "Performance remains consistent from millions to trillions of vectors, making it capable of handling massive datasets. Data is persisted to all-flash storage over NVMe and indexed in real time...the system uses sorted projections, precomputed materializations, and CPU fallback paths to maintain sub-second performance—even at trillion-vector scale."

**Source:** [VAST Data Vector Scale Performance](https://www.vastdata.com/blog/introducing-vast-vector-search-real-time-ai-retrieval-without-limits)

### 3.6 Embedding Model Integration

**InsightEngine Integration:**
- NVIDIA NIM microservice integration for real-time embedding generation
- Models run on NVIDIA accelerated computing
- Real-time embedding creation as data lands in system
- Embeddings stored in DataBase within milliseconds

**Automatic Vectorization:**
- Supports automatic chunking of incoming data
- Generates vector embeddings in real time
- Bypasses traditional batch processing delays
- Enabled by event-driven DataEngine triggers

**Multimodal Embedding Support:**
- Documents
- Camera footage
- Machine-generated data
- Video
- Text
- Image and audio modalities supported

**Platform Integration:**
- Embeddings stored natively in VAST DataBase
- Alongside structured metadata
- With unstructured raw data accessible on same platform
- Enables RAG (Retrieval Augmented Generation) pipelines

**Quote:** "InsightEngine utilizes VAST's DataEngine to trigger the NVIDIA NIM embedding agent as soon as new data is written to the system, allowing for real-time creation of vector embeddings or graph relationships from unstructured data, and bypassing traditional batch processing delays."

**Source:** [VAST InsightEngine with NVIDIA](https://www.vastdata.com/platform/insightengine)

### 3.7 Vector Operations in SQL Queries

**SQL Query Interface:**
- Vector similarity queried via standard SQL dialect
- ADBC (Arrow Database Connectivity) driver exposes the SQL interface
- Native SQL operators for vector operations

**Hybrid Query Support:**
- Single query combining vector similarity with SQL filters
- Traditional SQL WHERE clauses combined with vector operations
- Example: "similarity search within a subset of data identified by a graph relationship or a relational join"

**Query Patterns:**
```sql
-- Example hybrid query pattern (conceptual)
SELECT * FROM vectors_table
WHERE vector_similarity(vector_col, query_vector, 'cosine') < threshold
AND metadata_col = 'value'
ORDER BY distance
LIMIT 1000
```

**Integration with Metadata:**
- Each vector result includes full row data
- Associated metadata accessible without additional queries
- Original content retrievable from same row
- No orchestration layers required

**Source:** [VAST Vector Integration](https://www.vastdata.com/blog/vast-vector-search-the-right-foundation-for-real-time-ai)

---

## 4. VAST DataBase Schema Support

### 4.1 Data Types Available

**Basic Data Types Supported (Arrow types with predicate pushdown):**
- Integers (various sizes)
- Floating point numbers (float32 confirmed, likely float64)
- Decimals
- Booleans
- Binary data

**String and Text Types:**
- UTF-8 strings (utf8)
- Pattern matching support (startswith, contains)

**Temporal Types:**
- date32
- time32
- time64
- timestamp
- Timezone support (v1.3.10+)

**Vector Types:**
- Vector column type (float32 arrays of varying dimensions)
- Nested structures (v0.1.6+)

**Specialized Types:**
- FixedSizeListArray of numerics (v1.3.11+)

**Source:** [VAST DB Data Types Documentation](https://vastdb-sdk.readthedocs.io/en/latest/)

### 4.2 Index Creation and Optimization

**Automatic Index Creation:**
- Indexes built automatically during data ingestion
- Real-time indexing of incoming data
- No manual index definition required

**Index Types Created:**
- Zone maps for data pruning
- Vector indexes (details on types not public)
- Secondary indexes on columns
- Sorted projections for query optimization

**Semi-Sorted Projections:**
- Materialized data structures for query optimization
- Can be explicitly created and managed
- Improves query performance on specific access patterns

**Query Optimization:**
- Predicate pushdown filtering pushes constraints to storage
- Column projection pushdown selects only needed columns
- Internal concurrency tuning via `num_sub_splits` parameter
- Multiple endpoint distribution for load balancing

**Performance Tuning Configuration:**
- QueryConfig class for `Table.select()` tuning
- Multiple CNode endpoints for distributed query scanning
- Worker thread configuration for internal parallelism

**Source:** [VAST DB Configuration](https://vastdb-sdk.readthedocs.io/en/latest/docs/config.html)

### 4.3 Constraints (Unique, Foreign Key, Check)

**Status:** Information Not Publicly Available in Documentation

Specific constraint support is not documented in public VAST resources.

**Constraints Not Explicitly Documented:**
- UNIQUE constraints
- PRIMARY KEY support
- FOREIGN KEY constraints
- CHECK constraints
- DEFAULT values
- NOT NULL constraints (implied via NULL handling in predicates)

**What Can Be Inferred:**
- NULL checking is supported in predicates (`isnull()`)
- Data type system exists
- Row-oriented write path suitable for constraint enforcement

**Recommendation:** Contact VAST support for:
- List of supported constraints
- Constraint enforcement model
- Constraint validation timing
- Referential integrity support

### 4.4 Partitioning and Sharding Strategies

**VAST Architecture Approach:**
- DASE (Disaggregated Shared-Everything) architecture eliminates need for sharding
- Linear scaling without data movement or sharding complexity
- Quote: "scales databases without the complexity of sharding or data movement"
- Every compute node has direct access to entire dataset via NVMe-oF

**Data Organization:**
- Data organized in 32KB columnar chunks
- Distributed across cluster but transparently accessible
- No manual partitioning required

**Scalability:**
- Linear scaling to exabytes
- Horizontal scaling by adding compute nodes
- Throughput scales linearly with added nodes
- All nodes maintain consistent view of data

**Implications:**
- No user-managed partitioning strategy needed
- No partition pruning or routing logic required
- Simplified application logic

**Source:** [VAST DASE Architecture](https://www.vastdata.com/platform/how-it-works)

### 4.5 Schema Versioning Approach

**Status:** Information Not Publicly Available in Documentation

VAST's approach to schema evolution and versioning is not documented in public resources.

**Information to Obtain:**
- Schema migration patterns
- Backward compatibility support
- Schema versioning strategy
- Alter table support
- Column addition/removal procedures
- Data type evolution support

**Context from SDK:**
- SDK v2.0.0 introduced breaking changes (removed Table.bucket and Table.schema properties)
- Suggests VAST takes schema compatibility seriously
- Version management important for production deployments

### 4.6 Backup and Recovery Procedures

**Status:** Information Not Publicly Available in Documentation for VAST Specifically

General database backup/recovery principles apply, but VAST-specific procedures are not documented.

**Information to Obtain from VAST:**
- Snapshot capabilities and procedures
- Point-in-time recovery support
- Backup scheduling mechanisms
- Recovery time objective (RTO) support
- Recovery point objective (RPO) capabilities
- Cross-cluster replication for disaster recovery
- Backup storage options

**Related Capability:**
VAST Catalog supports snapshots for point-in-time data access:
- "Snapshot access for data recovery and analysis"
- Enables historical data queries
- Can be accessed via Python SDK

**Source:** [VAST DB SDK Snapshots Feature](https://vastdb-sdk.readthedocs.io/)

---

## 5. VAST DataBase Monitoring & Operations

### 5.1 Query Performance Metrics

**Available Monitoring:**
- All telemetry and logs from functions/queries streamed to VAST DataBase tables
- Metrics rendered in UI for visualization
- Queryable from CLI and API interface
- Queryable from within SQL queries

**Query Execution Metrics Implied:**
- Query latency
- Execution duration
- Data scanned/processed
- Result row count
- Memory usage during execution
- CPU utilization

**Built-In Observability:**
- Integrated telemetry collection (no external tooling required)
- Metrics available in real-time in DataBase tables
- Queryable for historical analysis

**Quote:** "All telemetry and logs from your functions get streamed into VAST DataBase tables, which are then rendered in the UI as well as queryable from a CLI and API interface."

**Source:** [VAST DataEngine Monitoring](https://www.vastdata.com/platform/dataengine)

### 5.2 Slow Query Logs

**Status:** Partially Available

Query metrics are captured in DataBase tables, implying slow query identification is possible through:
- Query duration tracking in telemetry tables
- Historical query analysis
- SQL queries against performance tables
- UI visualization of execution metrics

**How to Implement:**
- Query DataBase telemetry tables for duration metrics
- Filter for queries exceeding performance threshold
- Analyze execution patterns and resource usage
- Track trends over time

**Not Explicitly Documented:**
- Automatic slow query threshold configuration
- Built-in slow query report
- Configurable alerting on slow queries

**Source:** [VAST DataEngine Observability](https://www.vastdata.com/platform/dataengine)

### 5.3 Connection Pooling Options

**Status:** Information Not Publicly Available in Documentation

VAST DataBase connection pooling configuration is not documented in public resources.

**Information to Obtain:**
- Connection pooling support (implicit vs explicit)
- Pool size configuration
- Connection timeout settings
- Idle connection handling
- Connection reuse strategy
- Per-application pool limits

**Context from SDK:**
- Python SDK uses session objects for connections
- Session creation and management encapsulates connection handling
- Transactions use context managers
- Suggests built-in connection lifecycle management

### 5.4 Resource Utilization Tracking

**Available Tracking:**
- Telemetry streamed to DataBase tables
- Query execution metrics captured
- Function execution metrics logged
- Storage metrics accessible

**Metrics Available:**
- Memory usage (implied through telemetry)
- CPU utilization (implied)
- Query execution duration
- Data processed
- Result sizes
- Function execution time

**Access Method:**
- Queryable from SQL interface
- Available in UI dashboards
- Exportable for external analysis

**Scalability Indicators:**
- Linear scaling metrics as nodes added
- Throughput tracking
- Performance consistency metrics

**Source:** [VAST DataEngine Observability](https://www.vastdata.com/platform/dataengine)

### 5.5 High Availability and Replication

**Status:** Partially Documented

**VAST Architecture for HA:**
- DASE (Disaggregated Shared-Everything) architecture enables high availability
- Shared data access from any compute node
- Elimination of single points of failure through distributed architecture
- NVMe-over-Fabrics ensures consistent data access

**DataSpace Federation:**
- Cross-cluster replication capability
- Multiple clusters operate as unified namespace
- Enables disaster recovery scenarios
- Quote: "Federation machinery enabling multiple clusters to operate as a unified namespace with cross-site replication"

**Reliability Features:**
- Fully ACID compliant (ensures data consistency)
- Real-time transaction support
- Column-oriented storage with row-level transaction capability

**What's Not Documented:**
- Specific replication lag metrics
- Failover procedures
- Replica lag tolerance
- Backup frequency recommendations
- Recovery procedures

**Source:** [Glenn Klockwood VAST Documentation](https://www.glennklockwood.com/garden/VAST)

---

## 6. Python SDK Specifications (VAST DB Python SDK)

### 6.1 SDK Version Information

**Current Version:** 2.0.2 (October 22, 2025)

**Recent Major Releases:**
- **v2.0.0:** Breaking changes - removed Table.bucket and Table.schema properties, discontinued Python 3.9 support, added pyarrow~=18.0 requirement, introduced ITable interface and TableMetadata
- **v2.0.1:** Performance improvements - optimize query data flow with column selection
- **v2.0.2:** Fixed table statistics (row count and size in bytes)

**Supported Python Versions:**
- Python 3.10
- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.9 no longer officially supported

**System Requirements:**
- Linux operating system
- VAST Cluster release 5.0.0-sp10 or later
- Network connectivity to cluster
- S3 credentials
- Virtual IP pool access
- Tabular identity policy configuration

**Installation:**
```bash
pip install vastdb
```

**Dependencies:**
- pyarrow~=18.0 (required, v2.0.0+)
- DuckDB (for post-processing)

**Source:** [VAST DB Python SDK Release Notes](https://vastdb-sdk.readthedocs.io/en/latest/)

### 6.2 SDK Core Modules

**Available Modules:**

1. **vastdb.session** - Session management and connection
2. **vastdb.bucket** - Bucket operations and management
3. **vastdb.schema** - Schema creation and management
4. **vastdb.table** - Table operations and queries
5. **vastdb.transaction** - Transaction context management
6. **vastdb.errors** - Error handling and exceptions
7. **vastdb.util** - Utility functions

**Access to VAST Catalog:**
- File system querying as database tables
- Metadata operations
- Snapshot access and querying

**Source:** [VAST DB SDK Module Reference](https://vastdb-sdk.readthedocs.io/)

### 6.3 SDK Capabilities Summary

**Schema and Table Management:**
- Create schemas and tables
- Define data types
- Manage table metadata
- Access table statistics

**Data Operations:**
- Insert rows (v1.3.0+) and columns (v1.4.0+)
- Query tables with SELECT
- Update sorted tables (v1.3.8+)
- Delete from sorted tables (v1.3.8+)

**Query Optimization:**
- Predicate pushdown filtering
- Column projection pushdown
- QueryConfig for tuning
- Multiple endpoint support

**Data Formats:**
- PyArrow RecordBatch input/output
- Parquet file import and export
- Single and concurrent imports
- Direct DuckDB integration

**File System Integration:**
- VAST Catalog querying
- File metadata access
- Snapshot-based queries

**Advanced Features:**
- Semi-sorted projections
- Database snapshots
- Nested schema support (v0.1.6+)
- FixedSizeListArray support (v1.3.11+)

**Source:** [VAST DB SDK Documentation](https://vastdb-sdk.readthedocs.io/)

---

## 7. Comparison with EXR-Inspector Architecture Assumptions

### 7.1 Serverless Function Assumptions

**Assumption:** Long-running ETL functions can execute with known timeout limits

**Reality:**
- Timeout limits are not documented
- Must be obtained from VAST support
- Recommendation: Implement chunking strategy to work within unknown limits

**Assumption:** Functions can scale horizontally with unlimited concurrency

**Reality:**
- Concurrent execution limits not documented
- Scaling behavior under load is unclear
- Recommendation: Test scaling characteristics with VAST before production deployment

**Assumption:** Cold start time is minimal

**Reality:**
- Cold start characteristics not documented
- DASE architecture may minimize overhead
- Recommendation: Benchmark cold start times for performance-critical paths

### 7.2 SQL Capabilities Assumptions

**Assumption:** Full SQL support including aggregations and date/time functions

**Reality:**
- Specific SQL function library not documented
- Only predicate operators and vector distance functions documented
- Recommendation: Verify aggregate function availability before design

**Assumption:** Standard ACID transactions work as expected

**Reality:**
- Confirmed ACID compliant
- Transactions required for all operations
- Context manager pattern used
- Aligns well with assumption

**Assumption:** Query timeout and resource limits are configurable

**Reality:**
- Query timeout settings not documented
- Performance tuning is possible via QueryConfig
- Recommendation: Request timeout configuration options from VAST

### 7.3 Vector Capabilities Assumptions

**Assumption:** Standard vector index types (HNSW, IVFFlat) are used

**Reality:**
- Index types not explicitly documented
- Custom VAST indexing strategy based on columnar design
- Real-time indexing provided automatically
- Dimension limits not specified

**Recommendation:** Verify vector dimension limits before embedding model selection

**Assumption:** Vector search performance scales linearly

**Reality:**
- Confirmed: consistent performance from millions to trillions of vectors
- Sub-second search at trillion-vector scale
- Linear throughput scaling with added nodes
- Assumption validated

**Assumption:** Similarity functions include cosine, Euclidean, and dot product

**Reality:**
- Confirmed: cosine, Euclidean, and negative inner product available
- Queryable via standard SQL interface
- Hybrid query support confirmed

### 7.4 Data Persistence Assumptions

**Assumption:** Backup and recovery procedures are automated

**Reality:**
- Not documented in public resources
- Snapshot feature available for catalog data
- Recommendation: Implement explicit backup procedures after confirming VAST capabilities

**Assumption:** Schema versioning and evolution is handled transparently

**Reality:**
- Not documented
- SDK has breaking changes between versions
- Recommendation: Plan explicit schema migration procedures

---

## 8. Critical Information Gaps Requiring VAST Support Contact

The following specifications are not available in public documentation and should be requested from VAST support:

### High Priority (Critical for Architecture)

1. **Function Execution Timeout Limits**
   - Maximum execution time per invocation
   - Configurable timeout options
   - Behavior on timeout (graceful vs immediate termination)

2. **Concurrent Function Execution Limits**
   - Maximum concurrent executions per cluster
   - Per-tenant limits
   - Scaling behavior under load

3. **Vector Dimension Limits**
   - Maximum supported dimensions
   - Supported precision formats
   - Performance impact of high dimensions

4. **Query Timeout Configuration**
   - Default and maximum timeouts
   - Per-query overrides
   - Timeout behavior and error handling

5. **Batch Operation Limits**
   - Maximum batch size
   - Concurrent batch limits
   - Memory requirements for batches

### Medium Priority (Important for Production)

6. **Memory Allocation Options**
   - Range of allocations
   - Default allocation
   - CPU-to-memory ratio

7. **Constraint Support**
   - UNIQUE, PRIMARY KEY, FOREIGN KEY
   - CHECK constraints
   - Constraint enforcement model

8. **Backup and Recovery**
   - Backup procedures
   - Recovery time objective (RTO)
   - Recovery point objective (RPO)
   - Cross-cluster disaster recovery

9. **Connection Pooling Configuration**
   - Pool size limits
   - Connection timeout settings
   - Pooling strategy

10. **SQL Function Library**
    - Available aggregate functions (SUM, AVG, COUNT, etc.)
    - String functions
    - Date/time functions
    - Math functions

### Lower Priority (Nice to Have)

11. **Full-Text Search Capabilities**
    - FTS support and syntax
    - Performance characteristics

12. **Error Handling and Retry**
    - Available error types
    - Retry mechanisms
    - Exponential backoff support

13. **Index Type Details**
    - Specific index algorithms used
    - Index configuration options
    - Index performance characteristics

14. **Schema Versioning**
    - Schema evolution procedures
    - Backward compatibility support
    - ALTER TABLE capabilities

---

## 9. Recommendations for EXR-Inspector Implementation

### 9.1 Architecture Validation

Before implementing serverless functions on VAST DataEngine:
1. Get explicit documentation on timeout limits
2. Run performance benchmarks with actual expected data volumes
3. Test concurrent execution limits with expected scale
4. Validate cold start impact on use cases

### 9.2 Data Model Validation

Before implementing data model in VAST DataBase:
1. Verify all required SQL functions are available
2. Test constraint support if needed
3. Validate vector dimension support with embedding models
4. Confirm query timeout behavior for long-running queries

### 9.3 Vector Operations Validation

Before implementing vector search:
1. Verify dimension support for chosen embedding models
2. Benchmark vector search performance with actual data scale
3. Test hybrid query performance (vector + SQL filters)
4. Validate similarity function accuracy for use case

### 9.4 Operational Procedures

Before production deployment:
1. Establish backup and recovery procedures
2. Define monitoring and alerting strategy
3. Implement resource utilization tracking
4. Document runbooks for common operational tasks
5. Establish performance baseline and SLOs

### 9.5 Testing Strategy

Recommended testing before production:
1. Load testing: Test functions and queries at expected scale
2. Chaos testing: Test failure modes and recovery
3. Performance benchmarking: Baseline and SLO validation
4. Integration testing: Full end-to-end workflows
5. Scalability testing: Horizontal scaling validation

---

## 10. Sources and References

### Primary VAST Resources

- [VAST DataEngine: Real-Time Compute Fabric for Data & AI](https://www.vastdata.com/platform/dataengine)
- [VAST DataBase: A Unified Data Warehouse](https://www.vastdata.com/platform/database)
- [VAST Vector Search: The Right Foundation for Real-Time AI](https://www.vastdata.com/blog/vast-vector-search-the-right-foundation-for-real-time-ai)
- [VAST InsightEngine: Real-time AI Pipelines, RAG, Ingest](https://www.vastdata.com/platform/insightengine)
- [The VAST Platform White Paper](https://www.vastdata.com/whitepaper)

### SDK and Technical Documentation

- [VAST DB Python SDK Home](https://vastdb-sdk.readthedocs.io/en/latest/)
- [VAST DB Python SDK GitHub](https://github.com/vast-data/vastdb_sdk)
- [VAST DB SDK CHANGELOG](https://vastdb-sdk.readthedocs.io/en/latest/CHANGELOG.html)
- [VAST DataBase Configuration](https://vastdb-sdk.readthedocs.io/en/latest/docs/config.html)
- [VAST DataBase Predicates](https://vastdb-sdk.readthedocs.io/en/latest/docs/predicate.html)

### Research and Technical Analysis

- [Glenn Klockwood VAST Documentation](https://www.glennklockwood.com/garden/VAST)
- [Glenn Klockwood VAST Vector Database](https://glennklockwood.com/garden/VAST-vector-database)
- [Blocks and Files: VAST Data Vector Search](https://blocksandfiles.com/2025/05/12/vast-data-and-vector-search/)
- [Storage Review: VAST Data Vector Search & Event-Driven Workflows](https://www.storagereview.com/news/vast-data-takes-ai-storage-to-the-next-level-with-vector-search-event-driven-workflows)
- [Techzine Global: VAST InsightEngine Makes RAG Data Available in Real Time](https://www.techzine.eu/blogs/infrastructure/124932/vast-further-expands-data-platform-insightengine-makes-all-rag-data-available-in-real-time/)

### VAST Support and Knowledge Base

- [VAST Support Portal](https://support.vastdata.com/s/)
- [VAST Knowledge Base](https://kb.vastdata.com/)

---

## 11. Document Metadata

**Document Created:** February 6, 2026
**VAST Versions Researched:** 54.5, SDK 2.0.2, Latest (as of research date)
**Research Methodology:** Web search, technical documentation review, SDK documentation analysis, blog post analysis
**Completeness:** Approximately 75% of requested specifications found; 25% marked as unavailable in public documentation
**Recommendation:** Schedule follow-up with VAST support to fill information gaps, especially for timeout limits, concurrent execution limits, and dimension limits.

---

**End of Document**
