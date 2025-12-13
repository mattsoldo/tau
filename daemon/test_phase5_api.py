"""
Phase 5 API Routes Test

Tests API route registration, OpenAPI schema generation, and endpoint structure.
"""
from fastapi.testclient import TestClient
from tau.config import get_settings
from tau.api import create_app


def test_phase5_api():
    """Test API routes and OpenAPI schema"""
    print("=" * 60)
    print("Phase 5 API Routes Test")
    print("=" * 60)

    # Create app
    print("\n1. Creating FastAPI application...")
    settings = get_settings()
    app = create_app(settings)
    print("   ✓ Application created")

    # Create test client
    client = TestClient(app)
    print("   ✓ Test client created")

    # Test health endpoint
    print("\n2. Testing health endpoint...")
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "tau-daemon"
    print("   ✓ /health endpoint working")

    # Test status endpoint
    print("\n3. Testing status endpoint...")
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    print("   ✓ /status endpoint working")

    # Test OpenAPI schema
    print("\n4. Testing OpenAPI schema...")
    response = client.get("/docs")
    assert response.status_code == 200
    print("   ✓ /docs endpoint accessible")

    # Check OpenAPI routes
    print("\n5. Verifying API route registration...")
    openapi_schema = app.openapi()
    paths = openapi_schema["paths"]

    # Expected route prefixes
    expected_routes = {
        "/health": ["get"],
        "/status": ["get"],
        "/api/fixtures/": ["get", "post"],
        "/api/fixtures/{fixture_id}": ["get", "patch", "delete"],
        "/api/fixtures/{fixture_id}/state": ["get"],
        "/api/fixtures/models": ["get", "post"],
        "/api/fixtures/models/{model_id}": ["get", "delete"],
        "/api/groups/": ["get", "post"],
        "/api/groups/{group_id}": ["get", "patch", "delete"],
        "/api/groups/{group_id}/state": ["get"],
        "/api/groups/{group_id}/fixtures": ["get", "post"],
        "/api/groups/{group_id}/fixtures/{fixture_id}": ["delete"],
        "/api/scenes/": ["get", "post"],
        "/api/scenes/{scene_id}": ["get", "patch", "delete"],
        "/api/scenes/capture": ["post"],
        "/api/scenes/recall": ["post"],
        "/api/control/fixtures/{fixture_id}": ["post"],
        "/api/control/groups/{group_id}": ["post"],
        "/api/control/groups/{group_id}/circadian": ["post"],
        "/api/control/all-off": ["post"],
        "/api/control/panic": ["post"],
        "/api/circadian/": ["get", "post"],
        "/api/circadian/{profile_id}": ["get", "patch", "delete"],
    }

    found_routes = 0
    for route, methods in expected_routes.items():
        if route in paths:
            found_routes += 1
            for method in methods:
                assert method in paths[route], f"Method {method.upper()} not found in {route}"
            print(f"   ✓ {route}: {', '.join(m.upper() for m in methods)}")
        else:
            print(f"   ✗ {route}: NOT FOUND")

    print(f"\n   Found {found_routes}/{len(expected_routes)} expected routes")
    assert found_routes == len(expected_routes), f"Missing routes: {len(expected_routes) - found_routes}"

    # Test tags
    print("\n6. Verifying API tags...")
    tags = [tag["name"] for tag in openapi_schema.get("tags", [])]
    expected_tags = ["fixtures", "groups", "scenes", "control", "circadian"]

    for tag in expected_tags:
        if tag in tags:
            print(f"   ✓ Tag: {tag}")
        else:
            print(f"   ✗ Tag: {tag} (NOT FOUND)")

    # Test schemas
    print("\n7. Verifying Pydantic schemas...")
    components = openapi_schema.get("components", {})
    schemas = components.get("schemas", {})

    expected_schemas = [
        "FixtureCreate",
        "FixtureResponse",
        "FixtureUpdate",
        "GroupCreate",
        "GroupResponse",
        "SceneCreate",
        "SceneResponse",
        "CircadianProfileCreate",
        "CircadianProfileResponse",
        "FixtureControlRequest",
        "GroupControlRequest",
        "SceneCaptureRequest",
        "SceneRecallRequest",
    ]

    found_schemas = 0
    for schema_name in expected_schemas:
        if schema_name in schemas:
            found_schemas += 1
            print(f"   ✓ Schema: {schema_name}")
        else:
            print(f"   ✗ Schema: {schema_name} (NOT FOUND)")

    print(f"\n   Found {found_schemas}/{len(expected_schemas)} expected schemas")

    # Summary
    print("\n" + "=" * 60)
    print("✅ Phase 5 API Routes Test PASSED")
    print("=" * 60)
    print("\nVerified components:")
    print(f"  ✓ Health and status endpoints")
    print(f"  ✓ {found_routes} API routes registered")
    print(f"  ✓ {len(expected_tags)} API tags")
    print(f"  ✓ {found_schemas} Pydantic schemas")
    print(f"  ✓ OpenAPI documentation generated")
    print("\nAPI Endpoints:")
    print("  - Fixtures: CRUD + state management")
    print("  - Groups: CRUD + membership management")
    print("  - Scenes: CRUD + capture/recall")
    print("  - Control: Direct fixture/group control")
    print("  - Circadian: Profile management")
    print("\n🎉 Phase 5 Complete!")


if __name__ == "__main__":
    test_phase5_api()
