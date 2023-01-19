// Employees

CREATE (Leslie:Employee {name: 'Leslie Peers', role: 'role 1'})

CREATE (Bernhard:Employee {name: 'Bernhard Marin ', role: 'role 2'})

CREATE (Joe:Employee {name: 'Joe Doe', role: 'role 3'})

CREATE (Berk:Employee {name: 'Berk Fiona', role: 'role 4'})

// Departments

CREATE (Sales:Department {name: 'Sales'})

CREATE (Marketing:Department {name: 'Marketing'})

// Relations

CREATE (Leslie)-[:WORKS_IN]->(Marketing)

CREATE (Bernhard)-[:WORKS_IN]->(Marketing)

CREATE (Joe)-[:WORKS_IN]->(Sales)

CREATE (Berk)-[:WORKS_IN]->(Sales)

//

CREATE (Bernhard)-[:MANAGES]->(Marketing)

CREATE (Berk)-[:MANAGES]->(Sales)


// MATCH (n) DETACH DELETE n