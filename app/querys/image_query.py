# from app.services.source_system_service import SourceSystemService

# source_system = SourceSystemService()

# def get_image_by_co_art(co_art: str):
#     conn = None
#     try:
#         conn = source_system.get_pooled_connection()
#         cursor = conn.cursor()
#         query = """
#         SELECT imagen_des FROM saArtImagen WHERE co_art = %s
#         """
#         cursor.execute(query, (co_art,))
#         row = cursor.fetchone()
#         cursor.close()
#         return row
#     except Exception as e:
#         print(e)
#         raise e
#     finally:
#         if conn:
#             conn.close()

