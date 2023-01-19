from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)
uri = os.getenv('URI')
user = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password), database="neo4j")


def filter_employees(tx, name=None, role=None):
    query = "MATCH (e: Employee)"
    if name:
        query += f" WHERE toLower(e.name) CONTAINS toLower('{name}')"
    if role:
        query += f" WHERE toLower(e.role) CONTAINS toLower('{role}')"
    query += " RETURN e, ID(e) as id"
    return tx.run(query).data()


def sort_employees(employees, sort):
    if sort == "name_asc":
        return sorted(employees, key=lambda x: x["name"])
    elif sort == "name_desc":
        return sorted(employees, key=lambda x: x["name"], reverse=True)
    return employees


@app.route('/employees', methods=['GET'])
def get_employees_route():
    name = request.args.get('name')
    role = request.args.get('role')
    sort = request.args.get('sort')
    with driver.session() as session:
        employees = session.read_transaction(filter_employees, name, role)
        employees = [{"name": result['e']['name'],
                      "role": result['e']['role'], "id": result['id']} for result in employees]
        employees = sort_employees(employees, sort)
    response = {'employees': employees}
    return jsonify(response)


def add_employee(tx, name, role, department):
    query = "CREATE (e:Employee {name:$name, role:$role})" \
            "CREATE (d:Department {name:$department})" \
            "CREATE (e)-[:WORKS_IN]->(d)"
    tx.run(query, name=name, role=role, department=department)


@app.route('/employees', methods=['POST'])
def add_employee_route():
    if request.json is None:
        return jsonify({"error": "Request body can not be empty"}), 400
    name = request.json.get("name")
    role = request.json.get("role")
    department = request.json.get("department")
    if name is None or role is None or department is None:
        return jsonify({"error": "All fields are required"}), 400
    with driver.session() as session:
        result = session.run("MATCH (e:Employee) WHERE e.name = $name RETURN COUNT(e) as count", name=name).single()
        if result['count'] > 0:
            return jsonify({"error": "Employee is already in the database."}), 400
        session.write_transaction(add_employee, name, role, department)
        return jsonify({"message": "Employee has been added successfully."}), 201


def update_employee(tx, employee_id, name=None, role=None, department=None):
    query = "MATCH (e: Employee) WHERE ID(e) = $employee_id SET "
    updates = []
    if name is not None:
        updates.append("e.name = $name")
    if role is not None:
        updates.append("e.role = $role")
    if department is not None:
        updates.append("e.department = $department")
    if not updates:
        return {"error": "No updates provided"}
    query += ", ".join(updates)
    result = tx.run(query, employee_id=employee_id, name=name, role=role, department=department)
    if result.consume().counters.nodes_created > 0:
        return {"error": "Employee not found"}
    return {"message": "Employee has been updated successfully"}


@app.route('/employees/<int:id>', methods=['PUT'])
def update_employee_route(id):
    name = request.json.get('name')
    role = request.json.get('role')
    department = request.json.get('department')
    with driver.session() as session:
        res = session.run("MATCH (e:Employee) WHERE ID(e) = $id RETURN e", id=id).single()
        if res is None:
            return jsonify({"error": "Employee not found."}), 404
        result = session.write_transaction(update_employee, id, name, role, department)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200


def delete_employee(tx, id):
    query = "MATCH (e: Employee) WHERE ID(e) = $id DETACH DELETE e"
    tx.run(query, id=id)


@app.route('/employees/<int:id>', methods=['DELETE'])
def delete_employee_route(id):
    with driver.session() as session:
        result = session.run("MATCH (e:Employee)-[r:MANAGES]->(d:Department)"
                             " WHERE ID(e) = $id RETURN d.name", id=id).single()
        if result is None:
            session.write_transaction(delete_employee, id)
            return jsonify({"message": "Employee has been deleted successfully"}), 200
        else:
            department_name = result["d.name"]
            session.write_transaction(delete_employee, id)
            return jsonify({"message": f"Employee and its department {department_name} has been deleted successfully."}), 200


@app.route('/employees/<int:id>/subordinates', methods=['GET'])
def get_subordinates(id):
    with driver.session() as session:
        result = session.run("MATCH (m:Employee)-[r:MANAGES]->(d:Department) WHERE ID(m) = $id "
                             "RETURN d.name as department_name", id=id).single()
        if not result:
            return jsonify({"error": "Employee not found or has no department to manage"}), 404
        department_name = result["department_name"]
        query = "MATCH (e:Employee)-[r:WORKS_IN]->(d:Department) " \
                "WHERE d.name = $department_name RETURN e.name as name"
        results = session.run(query, department_name=department_name).data()
        subordinates = [{"name": result["name"]} for result in results]
        return jsonify(subordinates), 200


@app.route('/employees/<int:id>', methods=['GET'])
def get_employee_info(id):
    with driver.session() as session:
        query = "MATCH (e:Employee)-[r:WORKS_IN]->(d:Department)<-[:MANAGES]-(m:Employee)," \
                "(em:Employee)-[rel:WORKS_IN]->(d)" \
                "WHERE ID(e) = $id " \
                "RETURN d.name as department_name, m.name as manager," \
                " count(rel) as number_of_employees"
        result = session.run(query, id=id).single()
        if not result:
            return jsonify({"error": "Employee not found or has no department"}), 404
        department_name = result["department_name"]
        manager = result["manager"]
        number_of_employees = result["number_of_employees"]
        return jsonify({"department_name": department_name, "manager": manager,
                        "number_of_employees": number_of_employees}), 200


def get_departments(tx, name=None, sort=None):
    query = "MATCH (e:Employee)-[r]->(d:Department)"
    conditions = []
    if name is not None:
        conditions.append("toLower(d.name) CONTAINS toLower($name)")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " RETURN d.name as name, count(r) as number_of_employees,  ID(d) as id"
    if sort == "name_asc":
        query += " ORDER BY d.name"
    elif sort == "name_desc":
        query += " ORDER BY d.name DESC"
    elif sort == "e_asc":
        query += " ORDER BY number_of_employees"
    elif sort == "e_desc":
        query += " ORDER BY number_of_employees DESC"
    results = tx.run(query, name=name).data()
    departments = [{"name": result['name'], "number_of_employees": result['number_of_employees'], "id": result['id']}
                   for result in results]
    return departments


@app.route('/departments', methods=['GET'])
def get_departments_route():
    name = request.args.get('name')
    sort = request.args.get('sort')

    with driver.session() as session:
        departments = session.read_transaction(get_departments, name, sort)
        return jsonify(departments), 200


def get_employees_by_department(tx, id):
    query = "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) WHERE ID(d) = $id RETURN e"
    results = tx.run(query, id=id).data()
    employees = [{"name": result['e']['name'], "role": result['e']['role']} for result in results]
    return employees


@app.route('/departments/<int:id>/employees', methods=['GET'])
def get_department_employees(id):
    with driver.session() as session:
        employees = session.read_transaction(get_employees_by_department, id)
        return jsonify(employees), 200


if __name__ == '__main__':
    app.run()
